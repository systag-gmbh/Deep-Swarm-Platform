FROM ghcr.io/berriai/litellm:v1.81.12-stable

# Patch for https://github.com/BerriAI/litellm/issues/21891
# TypeError: 'NoneType' object is not a mapping when extra_body is None
COPY patch_extra_body.py /tmp/patch_extra_body.py
RUN python3 /tmp/patch_extra_body.py && rm /tmp/patch_extra_body.py
