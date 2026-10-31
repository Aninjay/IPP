FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 MPLBACKEND=Agg MPLCONFIGDIR=/tmp/mpl STATE_DIR=/data
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY kala_fest_allocator.py volunteers_CSV.csv icon.jpeg tapmi_logo.png ./
RUN useradd --system --uid 10001 appuser && mkdir /data && chown appuser /data
USER appuser
ENV PORT=5000
EXPOSE 5000
CMD ["python", "kala_fest_allocator.py"]
