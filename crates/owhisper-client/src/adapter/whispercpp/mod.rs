#[cfg(feature = "local")]
mod batch;
mod live;

#[derive(Clone, Default)]
pub struct WhisperCppAdapter;
