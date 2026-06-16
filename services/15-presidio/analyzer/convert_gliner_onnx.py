"""Export GLiNER model to ONNX format for use with gline-rs."""
from gliner import GLiNER

model = GLiNER.from_pretrained(
    "E3-JSI/gliner-multi-pii-domains-v1", load_tokenizer=True
)
model.export_to_onnx(save_dir="/opt/gliner-onnx", quantize=False, opset=19)
print("ONNX export complete: /opt/gliner-onnx")
