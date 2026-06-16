use std::sync::Arc;

use axum::{
    extract::State,
    http::StatusCode,
    routing::{get, post},
    Json, Router,
};
use gliner::model::{input::text::TextInput, params::Parameters, pipeline::span::SpanMode, GLiNER};
use orp::params::RuntimeParameters;
use serde::{Deserialize, Serialize};

#[derive(Deserialize)]
struct PredictRequest {
    text: String,
    labels: Vec<String>,
}

#[derive(Serialize)]
struct Entity {
    text: String,
    label: String,
    start: usize,
    end: usize,
    score: f32,
}

#[derive(Serialize)]
struct HealthResponse {
    status: String,
}

struct AppState {
    model: GLiNER<SpanMode>,
}

async fn health() -> Json<HealthResponse> {
    Json(HealthResponse {
        status: "healthy".to_string(),
    })
}

async fn predict(
    State(state): State<Arc<AppState>>,
    Json(req): Json<PredictRequest>,
) -> Result<Json<Vec<Entity>>, StatusCode> {
    let labels: Vec<&str> = req.labels.iter().map(|s| s.as_str()).collect();

    let input = TextInput::from_str(&[req.text.as_str()], &labels).map_err(|e| {
        eprintln!("Input error: {e}");
        StatusCode::BAD_REQUEST
    })?;

    let output = state.model.inference(input).map_err(|e| {
        eprintln!("Inference error: {e}");
        StatusCode::INTERNAL_SERVER_ERROR
    })?;

    let entities: Vec<Entity> = output
        .spans
        .into_iter()
        .flatten()
        .map(|s| {
            let (start, end) = s.offsets();
            Entity {
                text: s.text().to_string(),
                label: s.class().to_string(),
                start,
                end,
                score: s.probability(),
            }
        })
        .collect();

    Ok(Json(entities))
}

#[tokio::main]
async fn main() {
    let model_dir =
        std::env::var("GLINER_MODEL_DIR").unwrap_or_else(|_| "/opt/gliner-onnx".into());
    let threshold: f32 = std::env::var("GLINER_THRESHOLD")
        .unwrap_or_else(|_| "0.3".into())
        .parse()
        .expect("GLINER_THRESHOLD must be a float");
    let port = std::env::var("PORT").unwrap_or_else(|_| "5003".into());

    eprintln!("Loading GLiNER model from {model_dir} (threshold={threshold})...");

    let params = Parameters::default()
        .with_threshold(threshold)
        .with_max_length(Some(384));

    let model = GLiNER::<SpanMode>::new(
        params,
        RuntimeParameters::default(),
        format!("{model_dir}/tokenizer.json"),
        format!("{model_dir}/model.onnx"),
    )
    .expect("Failed to load GLiNER model");

    eprintln!("GLiNER model loaded successfully");

    let state = Arc::new(AppState { model });

    let app = Router::new()
        .route("/health", get(health))
        .route("/predict", post(predict))
        .with_state(state);

    let addr = format!("0.0.0.0:{port}");
    eprintln!("Listening on {addr}");

    let listener = tokio::net::TcpListener::bind(&addr)
        .await
        .expect("Failed to bind");
    axum::serve(listener, app).await.expect("Server error");
}
