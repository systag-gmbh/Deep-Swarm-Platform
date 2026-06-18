# v1.84.9
FROM ghcr.io/berriai/litellm@sha256:4147ee552189110d1c4c8f90e51ed98b69d222bd0ef9ca364c8f75e2865d2eb3

# Patch for https://github.com/BerriAI/litellm/issues/21891
# TypeError: 'NoneType' object is not a mapping when extra_body is None
COPY patch_extra_body.py /tmp/patch_extra_body.py
RUN python3 /tmp/patch_extra_body.py && rm /tmp/patch_extra_body.py
