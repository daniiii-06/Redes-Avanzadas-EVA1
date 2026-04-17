FROM python:3.10-slim

# Directorio de trabajo
WORKDIR /app

# Copia de archivos de dependencias
COPY requirements.txt .

# Instalación
RUN pip install --no-cache-dir -r requirements.txt

# Copia del script
COPY App.py .

# Comando de ejecución (mantiene el shell abierto en GNS3)
CMD ["/bin/bash"]
