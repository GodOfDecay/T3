# ClaimTrack Lite — legacy runtime. The base image is pinned BY DIGEST (python:2.7.18-slim):
# the platform's sandbox refuses a legacy image it cannot reproduce exactly.
FROM python@sha256:6c1ffdff499e29ea663e6e67c9b6b9a3b401d554d2c9f061f9a45344e3992363

WORKDIR /app
COPY claims-api /app/claims-api
COPY settlement-batch /app/settlement-batch
COPY db /app/db

ENV CLAIMTRACK_DB=/data/claimtrack.db \
    CLAIMTRACK_OUT=/data/out \
    FRAUD_URL=http://fraudscore:9000

EXPOSE 8080
CMD ["sh", "-c", "mkdir -p /data && python db/init.py && python claims-api/server.py"]
