FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt /app/
RUN pip install --no-cache-dir fastapi uvicorn numpy scipy astropy astroquery scikit-learn requests pillow
COPY . /app
ENV HOST=0.0.0.0
EXPOSE 8000
CMD ["python", "run.py"]
