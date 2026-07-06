use hypr_ws_client::client::Message;
use owhisper_interface::ListenParams;
use owhisper_interface::stream::StreamResponse;

use super::WhisperCppAdapter;
use crate::adapter::{RealtimeSttAdapter, append_path_if_missing, set_scheme_from_host};

// Realtime adapter for the in-process whisper.cpp server (crate
// `transcribe-whisper-local`), which exposes a `/v1/listen` WebSocket speaking
// the same StreamResponse / ControlMessage protocol as the Hyprnote proxy. This
// lets on-device Whisper transcribe live during a meeting instead of only in a
// post-capture batch. The server runs locally, so no auth header is sent.
impl RealtimeSttAdapter for WhisperCppAdapter {
    fn provider_name(&self) -> &'static str {
        "whispercpp"
    }

    fn is_supported_languages(
        &self,
        _languages: &[hypr_language::Language],
        _model: Option<&str>,
    ) -> bool {
        // Whisper is multilingual; the local server auto-handles the languages.
        true
    }

    fn supports_native_multichannel(&self) -> bool {
        true
    }

    fn build_ws_url(&self, api_base: &str, params: &ListenParams, channels: u8) -> url::Url {
        let mut url: url::Url = api_base.parse().expect("invalid api_base URL");

        set_scheme_from_host(&mut url);
        append_path_if_missing(&mut url, "listen");

        {
            let mut query = url.query_pairs_mut();

            if let Some(model) = &params.model {
                query.append_pair("model", model);
            }

            query.append_pair("channels", &channels.to_string());
            query.append_pair("sample_rate", &params.sample_rate.to_string());

            for lang in &params.languages {
                query.append_pair("language", lang.to_string().as_str());
            }

            if let Some(custom) = &params.custom_query {
                for (key, value) in custom {
                    query.append_pair(key, value);
                }
            }
        }

        url
    }

    fn build_auth_header(&self, _api_key: Option<&str>) -> Option<(&'static str, String)> {
        None
    }

    fn keep_alive_message(&self) -> Option<Message> {
        Some(Message::Text(
            serde_json::to_string(&owhisper_interface::ControlMessage::KeepAlive)
                .unwrap()
                .into(),
        ))
    }

    fn finalize_message(&self) -> Message {
        Message::Text(
            serde_json::to_string(&owhisper_interface::ControlMessage::Finalize)
                .unwrap()
                .into(),
        )
    }

    fn parse_response(&self, raw: &str) -> Vec<StreamResponse> {
        if let Ok(response) = serde_json::from_str::<StreamResponse>(raw) {
            return vec![response];
        }

        serde_json::from_str::<Vec<StreamResponse>>(raw).unwrap_or_default()
    }
}

#[cfg(test)]
mod tests {
    use hypr_language::ISO639;

    use super::WhisperCppAdapter;
    use crate::adapter::RealtimeSttAdapter;

    #[test]
    fn builds_local_v1_listen_ws_url() {
        let adapter = WhisperCppAdapter;
        let params = owhisper_interface::ListenParams {
            model: Some("QuantizedLargeTurbo".to_string()),
            languages: vec![ISO639::Ru.into()],
            sample_rate: 16_000,
            ..Default::default()
        };

        let url = adapter.build_ws_url("http://127.0.0.1:52321/v1", &params, 2);
        let s = url.as_str();

        assert_eq!(url.scheme(), "ws");
        assert!(s.contains("/v1/listen"), "url was {s}");
        assert!(s.contains("channels=2"));
        assert!(s.contains("sample_rate=16000"));
        assert!(s.contains("language=ru"));
        assert!(s.contains("model=QuantizedLargeTurbo"));
    }

    #[test]
    fn sends_no_auth_header() {
        let adapter = WhisperCppAdapter;
        assert_eq!(adapter.build_auth_header(Some("whatever")), None);
    }
}
