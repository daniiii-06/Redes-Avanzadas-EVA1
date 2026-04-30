Proyecto NetDevOps: Automatización Híbrida e IPsec

Este proyecto desarrolla una solución de NetDevOps para la automatización de infraestructura de red híbrida en un entorno simulado con GNS3. 
El objetivo principal es la configuración automática de un túnel VPN IPsec entre una Sede Central (Cisco) y una Sucursal (MikroTik/Arista) a través de un Router ISP.

La solución utiliza un nodo de automatización basado en Docker que ejecuta un script de Python, combinando protocolos tradicionales como SSH con tecnologías modernas de API REST

Herraminetas:

Lenguaje: Python 3.10 (Siguiendo estándares PEP8).  
Librerías Principales:Netmiko: 
Automatización SSH para equipos Cisco (R1 y R2).  
Requests: Interacción con la API REST nativa de R3.  
JSON: Parseo de respuestas y confirmación de éxito vía json.loads.  
Infraestructura: GNS3, Docker (Imagen python:3.10-slim).  

Integrantes:
Daniel Sagardia
Benjamin Sepúlveda
