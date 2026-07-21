use std::fs::File;
use std::io::BufWriter;
use std::path::{Path, PathBuf};
use std::time::Instant;

use hypr_audio_utils::{
    decode_vorbis_to_mono_wav_file, decode_vorbis_to_wav_file, mix_audio_f32,
    ogg_has_identical_channels,
};
use ractor::ActorProcessingErr;

use super::into_actor_err;

const FINAL_AUDIO_FILE: &str = "audio.mp3";
const WAV_FILE: &str = "audio.wav";
const OGG_FILE: &str = "audio.ogg";
const FLUSH_INTERVAL: std::time::Duration = std::time::Duration::from_millis(1000);

// A WAV file stores its data size in a 32-bit field, so it cannot physically
// exceed 4 GiB — hound's internal byte counter overflows (panic) at that point,
// which used to crash the recorder into a restart meltdown on very long
// recordings. Cap the WAV data well below that: 1.8 GiB is ~3.9 h of 16 kHz
// stereo f32 audio and also stays under the batch-transcription body limit
// (2 GiB), so a capped file can still be re-transcribed. On reaching the cap we
// finalize the file cleanly and simply stop writing to disk; the live session
// and transcript keep running.
const MAX_WAV_DATA_BYTES: u64 = 1_800_000_000;
const BYTES_PER_SAMPLE: u64 = 4; // 32-bit float

pub(super) struct DiskSink {
    writer: Option<hound::WavWriter<BufWriter<File>>>,
    writer_mic: Option<hound::WavWriter<BufWriter<File>>>,
    writer_spk: Option<hound::WavWriter<BufWriter<File>>>,
    wav_path: PathBuf,
    last_flush: Instant,
    is_stereo: bool,
    // Bytes of sample data written to the main `audio.wav` writer, tracked so we
    // can stop before the WAV 4 GiB / u32 limit. The main (possibly stereo)
    // writer grows fastest, so capping it also keeps the mono mic/spk writers
    // safely under the limit.
    main_data_bytes: u64,
    size_capped: bool,
}

pub(super) fn create_disk_sink(session_dir: &Path) -> Result<DiskSink, ActorProcessingErr> {
    let wav_path = session_dir.join(WAV_FILE);
    let ogg_path = session_dir.join(OGG_FILE);
    let encoded_path = session_dir.join(FINAL_AUDIO_FILE);
    let is_stereo = prepare_existing_audio_state(&encoded_path, &ogg_path, &wav_path)?;

    let stereo_spec = hound::WavSpec {
        channels: 2,
        sample_rate: super::super::SAMPLE_RATE,
        bits_per_sample: 32,
        sample_format: hound::SampleFormat::Float,
    };
    let mono_spec = hound::WavSpec {
        channels: 1,
        sample_rate: super::super::SAMPLE_RATE,
        bits_per_sample: 32,
        sample_format: hound::SampleFormat::Float,
    };

    let writer = if wav_path.exists() {
        hound::WavWriter::append(&wav_path)?
    } else if is_stereo {
        hound::WavWriter::create(&wav_path, stereo_spec)?
    } else {
        hound::WavWriter::create(&wav_path, mono_spec)?
    };

    let (writer_mic, writer_spk) = if is_debug_mode() {
        let mic_path = session_dir.join("audio_mic.wav");
        let spk_path = session_dir.join("audio_spk.wav");

        let mic_writer = if mic_path.exists() {
            hound::WavWriter::append(&mic_path)?
        } else {
            hound::WavWriter::create(&mic_path, mono_spec)?
        };

        let spk_writer = if spk_path.exists() {
            hound::WavWriter::append(&spk_path)?
        } else {
            hound::WavWriter::create(&spk_path, mono_spec)?
        };

        (Some(mic_writer), Some(spk_writer))
    } else {
        (None, None)
    };

    // Seed the counter with any pre-existing WAV data so resumed sessions still
    // honor the cap (file size minus the 44-byte header).
    let main_data_bytes = if wav_path.exists() {
        std::fs::metadata(&wav_path)
            .map(|m| m.len().saturating_sub(44))
            .unwrap_or(0)
    } else {
        0
    };

    Ok(DiskSink {
        writer: Some(writer),
        writer_mic,
        writer_spk,
        wav_path,
        last_flush: Instant::now(),
        is_stereo,
        main_data_bytes,
        size_capped: false,
    })
}

/// Returns true if `additional` sample bytes still fit under the WAV cap. On the
/// transition to "full" it finalizes all writers cleanly and marks the sink
/// capped, so subsequent writes become no-ops instead of overflowing hound.
fn reserve_main_bytes(sink: &mut DiskSink, additional: u64) -> bool {
    if sink.size_capped {
        return false;
    }
    if sink.main_data_bytes.saturating_add(additional) > MAX_WAV_DATA_BYTES {
        sink.size_capped = true;
        tracing::warn!(
            wav_bytes = sink.main_data_bytes,
            "audio WAV reached the size cap; finalizing file and stopping disk recording (session and transcript continue)"
        );
        let _ = finalize_writer(&mut sink.writer, Some(&sink.wav_path));
        let _ = finalize_writer(&mut sink.writer_mic, None);
        let _ = finalize_writer(&mut sink.writer_spk, None);
        return false;
    }
    sink.main_data_bytes += additional;
    true
}

pub(super) fn write_single(sink: &mut DiskSink, samples: &[f32]) -> Result<(), ActorProcessingErr> {
    let is_stereo = sink.is_stereo;
    let main_bytes = samples.len() as u64
        * BYTES_PER_SAMPLE
        * if is_stereo { 2 } else { 1 };

    if reserve_main_bytes(sink, main_bytes) {
        if let Some(writer) = sink.writer.as_mut() {
            if is_stereo {
                write_mono_as_stereo(writer, samples)?;
            } else {
                write_mono_samples(writer, samples)?;
            }
        }
    }

    flush_if_due(sink)?;
    Ok(())
}

pub(super) fn write_dual(
    sink: &mut DiskSink,
    mic: &[f32],
    spk: &[f32],
) -> Result<(), ActorProcessingErr> {
    let is_stereo = sink.is_stereo;
    let frames = mic.len().max(spk.len()) as u64;
    let main_bytes = frames * BYTES_PER_SAMPLE * if is_stereo { 2 } else { 1 };

    if reserve_main_bytes(sink, main_bytes) {
        if let Some(writer) = sink.writer.as_mut() {
            if is_stereo {
                write_interleaved_stereo(writer, mic, spk)?;
            } else {
                let mixed = mix_audio_f32(mic, spk);
                write_mono_samples(writer, &mixed)?;
            }
        }
    }

    // Debug mic/spk writers stop together with the main file: reserve_main_bytes
    // finalizes them (sets them to None) once the cap is hit.
    if let Some(writer_mic) = sink.writer_mic.as_mut() {
        write_mono_samples(writer_mic, mic)?;
    }

    if let Some(writer_spk) = sink.writer_spk.as_mut() {
        write_mono_samples(writer_spk, spk)?;
    }

    flush_if_due(sink)?;
    Ok(())
}

pub(super) fn finalize_disk_sink(sink: &mut DiskSink) -> Result<(), ActorProcessingErr> {
    finalize_writer(&mut sink.writer, Some(&sink.wav_path))?;
    finalize_writer(&mut sink.writer_mic, None)?;
    finalize_writer(&mut sink.writer_spk, None)?;

    if sink.wav_path.exists() {
        let encoded_path = sink.wav_path.with_extension("mp3");
        match hypr_mp3::encode_wav(&sink.wav_path, &encoded_path) {
            Ok(()) => {
                sync_file(&encoded_path);
                sync_dir(&encoded_path);
                std::fs::remove_file(&sink.wav_path)?;
                sync_dir(&sink.wav_path);
            }
            Err(error) => {
                tracing::error!("Encoding to mp3 failed, keeping WAV: {}", error);
                sync_file(&sink.wav_path);
                sync_dir(&sink.wav_path);
            }
        }
    }

    Ok(())
}

fn prepare_existing_audio_state(
    encoded_path: &Path,
    ogg_path: &Path,
    wav_path: &Path,
) -> Result<bool, ActorProcessingErr> {
    if encoded_path.exists() {
        decode_mp3_to_wav(encoded_path, wav_path)?;
        std::fs::remove_file(encoded_path)?;
        return Ok(wav_is_stereo(wav_path)?);
    }

    if ogg_path.exists() {
        let has_identical = ogg_has_identical_channels(ogg_path).map_err(into_actor_err)?;
        if has_identical {
            decode_vorbis_to_mono_wav_file(ogg_path, wav_path).map_err(into_actor_err)?;
        } else {
            decode_vorbis_to_wav_file(ogg_path, wav_path).map_err(into_actor_err)?;
        }
        std::fs::remove_file(ogg_path)?;
        return Ok(!has_identical);
    }

    if wav_path.exists() {
        return Ok(wav_is_stereo(wav_path)?);
    }

    Ok(true)
}

fn decode_mp3_to_wav(encoded_path: &Path, wav_path: &Path) -> Result<(), ActorProcessingErr> {
    let tmp_path = wav_path.with_extension("wav.tmp");
    if tmp_path.exists() {
        std::fs::remove_file(&tmp_path)?;
    }

    hypr_mp3::decode_to_wav(encoded_path, &tmp_path).map_err(into_actor_err)?;

    if wav_path.exists() {
        std::fs::remove_file(wav_path)?;
    }
    std::fs::rename(tmp_path, wav_path)?;
    Ok(())
}

fn wav_is_stereo(wav_path: &Path) -> Result<bool, hound::Error> {
    let reader = hound::WavReader::open(wav_path)?;
    Ok(reader.spec().channels == 2)
}

fn is_debug_mode() -> bool {
    cfg!(debug_assertions)
        || std::env::var("LISTENER_DEBUG")
            .map(|value| !value.is_empty() && value != "0" && value != "false")
            .unwrap_or(false)
}

fn flush_if_due(sink: &mut DiskSink) -> Result<(), hound::Error> {
    if sink.last_flush.elapsed() < FLUSH_INTERVAL {
        return Ok(());
    }

    flush_all(sink)
}

fn flush_all(sink: &mut DiskSink) -> Result<(), hound::Error> {
    if let Some(writer) = sink.writer.as_mut() {
        writer.flush()?;
    }
    if let Some(writer_mic) = sink.writer_mic.as_mut() {
        writer_mic.flush()?;
    }
    if let Some(writer_spk) = sink.writer_spk.as_mut() {
        writer_spk.flush()?;
    }
    sink.last_flush = Instant::now();
    Ok(())
}

fn write_mono_samples(
    writer: &mut hound::WavWriter<BufWriter<File>>,
    samples: &[f32],
) -> Result<(), hound::Error> {
    for sample in samples {
        writer.write_sample(*sample)?;
    }
    Ok(())
}

fn write_mono_as_stereo(
    writer: &mut hound::WavWriter<BufWriter<File>>,
    samples: &[f32],
) -> Result<(), hound::Error> {
    for sample in samples {
        writer.write_sample(*sample)?;
        writer.write_sample(*sample)?;
    }
    Ok(())
}

fn write_interleaved_stereo(
    writer: &mut hound::WavWriter<BufWriter<File>>,
    mic: &[f32],
    spk: &[f32],
) -> Result<(), hound::Error> {
    let frames = mic.len().max(spk.len());
    for i in 0..frames {
        writer.write_sample(mic.get(i).copied().unwrap_or(0.0))?;
        writer.write_sample(spk.get(i).copied().unwrap_or(0.0))?;
    }
    Ok(())
}

fn finalize_writer(
    writer: &mut Option<hound::WavWriter<BufWriter<File>>>,
    path: Option<&Path>,
) -> Result<(), hound::Error> {
    if let Some(mut writer) = writer.take() {
        writer.flush()?;
        writer.finalize()?;

        if let Some(path) = path {
            sync_file(path);
        }
    }
    Ok(())
}

fn sync_file(path: &Path) {
    if let Ok(file) = File::open(path) {
        let _ = file.sync_all();
    }
}

fn sync_dir(path: &Path) {
    if let Some(parent) = path.parent()
        && let Ok(dir) = File::open(parent)
    {
        let _ = dir.sync_all();
    }
}

#[cfg(test)]
mod tests {
    use tempfile::tempdir;

    use crate::actors::SAMPLE_RATE;

    use super::*;

    #[test]
    fn create_disk_sink_decodes_existing_mp3_to_wav() {
        let dir = tempdir().unwrap();
        let session_dir = dir.path().join("session");
        std::fs::create_dir_all(&session_dir).unwrap();
        std::fs::copy(
            hypr_data::english_1::AUDIO_MP3_PATH,
            session_dir.join(FINAL_AUDIO_FILE),
        )
        .unwrap();

        let _sink = create_disk_sink(&session_dir).unwrap();

        assert!(session_dir.join(WAV_FILE).exists());
        assert!(!session_dir.join(FINAL_AUDIO_FILE).exists());
    }

    #[test]
    fn create_disk_sink_prefers_existing_mp3_over_stale_wav() {
        let dir = tempdir().unwrap();
        let session_dir = dir.path().join("session");
        std::fs::create_dir_all(&session_dir).unwrap();
        let encoded_path = session_dir.join(FINAL_AUDIO_FILE);
        let wav_path = session_dir.join(WAV_FILE);
        std::fs::copy(hypr_data::english_1::AUDIO_MP3_PATH, &encoded_path).unwrap();
        write_test_wav(&wav_path, 128);
        let original_frames = decoded_frame_count(&encoded_path);

        let mut sink = create_disk_sink(&session_dir).unwrap();
        write_single(&mut sink, &vec![0.0; SAMPLE_RATE as usize]).unwrap();
        finalize_disk_sink(&mut sink).unwrap();

        assert!(!wav_path.exists());
        assert!(encoded_path.exists());
        assert!(decoded_frame_count(&encoded_path) > original_frames);
    }

    #[test]
    fn create_disk_sink_keeps_legacy_wav_for_append() {
        let dir = tempdir().unwrap();
        let session_dir = dir.path().join("session");
        std::fs::create_dir_all(&session_dir).unwrap();
        std::fs::copy(hypr_data::english_1::AUDIO_PATH, session_dir.join(WAV_FILE)).unwrap();

        let _sink = create_disk_sink(&session_dir).unwrap();

        assert!(session_dir.join(WAV_FILE).exists());
        assert!(!session_dir.join(FINAL_AUDIO_FILE).exists());
    }

    fn decoded_frame_count(path: &Path) -> usize {
        use hypr_audio_utils::Source;

        let source = hypr_audio_utils::source_from_path(path).unwrap();
        let channels = u16::from(source.channels()).max(1) as usize;
        source.count() / channels
    }

    fn write_test_wav(path: &Path, frames: usize) {
        let spec = hound::WavSpec {
            channels: 1,
            sample_rate: SAMPLE_RATE,
            bits_per_sample: 32,
            sample_format: hound::SampleFormat::Float,
        };
        let mut writer = hound::WavWriter::create(path, spec).unwrap();
        for _ in 0..frames {
            writer.write_sample(0.0f32).unwrap();
        }
        writer.finalize().unwrap();
    }
}
