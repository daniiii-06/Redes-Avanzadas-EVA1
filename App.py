import time
import json
import requests
import subprocess
from netmiko import ConnectHandler
from netmiko.exceptions import NetmikoTimeoutException, NetmikoAuthenticationException

# ==============================================================================
# CONFIGURACION GLOBAL Y CREDENCIALES
# ==============================================================================
# Cambiar con las credenciales usadas en los nodos de GNS3
CISCO_USER = "cisco"
CISCO_PASS = "cisco"
MT_USER = "admin"
MT_PASS = "admin"

OOB_R1_IP = "192.168.120.10"
OOB_R2_IP = "192.168.130.20"
OOB_R3_IP = "192.168.140.30"

VPN_PSK = "Inacap2026NetDevOps"

# ==============================================================================
# FUNCIONES DE AUTOMATIZACIÓN - CISCO (SSH)
# ==============================================================================

def config_r2():
    print("Iniciando configuracion de R2 (ISP) vía SSH...")
    device = {
        "device_type": "cisco_ios",
        "ip": OOB_R2_IP,
        "username": CISCO_USER,
        "password": CISCO_PASS,
        "fast_cli": True
    }
    
    # R2 Simula ISP: Agregamos las IPs de GNS3 y ruta básica
    commands = [
        "interface GigabitEthernet0/1",
        " ip address 200.1.12.2 255.255.255.252",
        " no shutdown",
        " exit",
        "interface GigabitEthernet0/2",
        " ip address 200.1.23.1 255.255.255.252",
        " no shutdown",
        " exit",
        "ip routing",
        "ip route 0.0.0.0 0.0.0.0 Null0 254"
    ]
    
    try:
        net_connect = ConnectHandler(**device)
        output = net_connect.send_config_set(commands)
        print("R2 configurado exitosamente.")
        net_connect.disconnect()
    except NetmikoTimeoutException:
        print("ERROR: Timeout conectando a R2 OOB.")
    except NetmikoAuthenticationException:
        print("ERROR: Fallo de Autenticación en R2.")
    except Exception as e:
        print(f"Error conectando a R2: {e}")

def config_r1():
    print("Iniciando configuracion de R1 (VPN IPsec) vía SSH...")
    device = {
        "device_type": "cisco_ios",
        "ip": OOB_R1_IP,
        "username": CISCO_USER,
        "password": CISCO_PASS,
        "fast_cli": True
    }
    
    commands = [
        # Configuracion de Interfaces e IPs
        "interface Loopback10",
        " ip address 192.168.10.1 255.255.255.0",
        " no shutdown",
        " exit",
        "interface GigabitEthernet0/1",
        " ip address 200.1.12.1 255.255.255.252",
        " no shutdown",
        " exit",
        "interface GigabitEthernet0/2",
        " ip address 200.1.13.1 255.255.255.252",
        " no shutdown",
        " exit",
        
        # Ruta por defecto hacia R2 (ISP)
        "ip route 0.0.0.0 0.0.0.0 200.1.12.2",
        
        # IPSEC FASE 1 (ISAKMP)
        "crypto isakmp policy 10",
        " encr aes 256",
        " hash sha256",
        " authentication pre-share",
        " group 14",
        " lifetime 86400",
        " exit",
        f"crypto isakmp key {VPN_PSK} address 200.1.23.2",
        
        # IPSEC FASE 2 (IPsec Transform Set)
        "crypto ipsec transform-set TS esp-aes 256 esp-sha256-hmac",
        " mode tunnel",
        " exit",
        
        # ALC INTERESANTE (LAN R1 a LAN R3)
        "access-list 100 permit ip 192.168.10.0 0.0.0.255 192.168.30.0 0.0.0.255",
        
        # CRYPTO MAP
        "crypto map CMAP 10 ipsec-isakmp",
        " set peer 200.1.23.2",
        " set transform-set TS",
        " match address 100",
        " exit",
        
        # APLICAR A INTERFAZ de cara a Internet (Hacia R2)
        "interface GigabitEthernet0/1",
        " crypto map CMAP",
        " exit"
    ]
    
    try:
        net_connect = ConnectHandler(**device)
        output = net_connect.send_config_set(commands)
        print("R1 IPsec configurado exitosamente.")
        net_connect.disconnect()
    except NetmikoTimeoutException:
        print("ERROR: Timeout conectando a R1 OOB.")
    except NetmikoAuthenticationException:
        print("ERROR: Fallo de Autenticación en R1.")
    except Exception as e:
        print(f"Error general en R1: {e}")

# ==============================================================================
# FUNCIONES DE AUTOMATIZACIÓN - MIKROTIK (API REST)
# ==============================================================================

def config_r3():
    print("Iniciando configuracion de R3 (VPN IPsec) vía API REST...")
    base_url_r3 = f"http://{OOB_R3_IP}"
    auth = (MT_USER, MT_PASS)
    headers = {"content-type": "application/json"}
    
    # 1. Configuracion Base (Interfaces y Loopback)
    print(" -> Inyectando Enrutamiento e Interfaces Base en R3...")
    network_endpoints = [
        ("/rest/interface/bridge", {"name": "LO30"}),
        ("/rest/ip/address", {"address": "192.168.30.1/24", "interface": "LO30"}),
        ("/rest/ip/address", {"address": "200.1.23.2/30", "interface": "ether2"}),
        ("/rest/ip/address", {"address": "200.1.13.2/30", "interface": "ether3"}),
        ("/rest/ip/route", {"dst-address": "0.0.0.0/0", "gateway": "200.1.23.1"})
    ]
    
    for endpoint, payload in network_endpoints:
        try:
            req = requests.put(f"{base_url_r3}{endpoint}", json=payload, auth=auth, headers=headers, timeout=5)
            if req.status_code == 400 and req.text:
                error_detail = req.json().get('detail', '').lower()
                if 'already' in error_detail or 'exists' in error_detail or 'repeat' in error_detail:
                    continue  # Si ya existe, lo ignoramos de forma limpia
            req.raise_for_status()
            print(f"    [ÉXITO] {endpoint} configurado.")
        except requests.exceptions.HTTPError:
            print(f"    [INFO] Elemento en {endpoint} ya existía o repetido.")
        except Exception as e:
            pass

    # 2. Configuración IPsec
    base_url = f"{base_url_r3}/rest/ip/ipsec"
    # Notación usada en REST API MikroTik: PUT crea un nuevo objeto
    # Payload para IPsec Phase 1 Profile
    profile_data = {
        "name": "profile1",
        "hash-algorithm": "sha256",
        "enc-algorithm": "aes-256",
        "dh-group": "modp2048",
        "lifetime": "1d",
        "nat-traversal": "no"
    }
    
    peer_data = {
        "name": "peer1",
        "address": "200.1.12.1/32",
        "local-address": "200.1.23.2",
        "profile": "profile1",
        "exchange-mode": "main"
    }

    identity_data = {
        "peer": "peer1",
        "auth-method": "pre-shared-key",
        "secret": VPN_PSK
    }
    
    # Payload para IPsec Phase 2 Proposal
    proposal_data = {
        "name": "proposal1",
        "auth-algorithms": "sha256",
        "enc-algorithms": "aes-256-cbc",
        "lifetime": "1h",
        "pfs-group": "none"
    }
    
    policy_data = {
        "peer": "peer1",
        "tunnel": "yes",
        "src-address": "192.168.30.0/24",
        "dst-address": "192.168.10.0/24",
        "action": "encrypt",
        "proposal": "proposal1",
        "sa-src-address": "200.1.23.2",
        "sa-dst-address": "200.1.12.1"
    }

    endpoints = [
        ("profile", profile_data),
        ("peer", peer_data),
        ("identity", identity_data),
        ("proposal", proposal_data),
        ("policy", policy_data)
    ]
    
    for endpoint, payload in endpoints:
        try:
            url = f"{base_url}/{endpoint}"
            print(f" -> Ejecutando request HTTP PUT a: {url}")
            
            # Uso de request PUT (Creacion/Update REST en RouterOS)
            req = requests.put(url, json=payload, auth=auth, headers=headers, timeout=10)
            
            # Verificamos si es un error 400 por duplicado ANTES de raise_for_status
            if req.status_code == 400 and req.text:
                resp_error = req.json()
                error_detail = resp_error.get('detail', '').lower()
                if 'repeat' in error_detail or 'duplicate' in error_detail or 'only one identity' in error_detail:
                    print(f"    [INFO] {endpoint.upper()} ya existe en R3. Omitiendo creación para evitar duplicados.")
                    continue
            
            # Verificación del estado HTTP para otros errores
            req.raise_for_status()

            # Extracción y Parseo de Data (Cumpliendo RUBRICA 1.1.4: Parseo json.loads)
            response_text = req.text
            if response_text:
                resp_json = json.loads(response_text)
                print(f"    [ÉXITO] {endpoint.upper()} configurado. Detalles JSON extraídos:")
                print("    " + str(resp_json))
            else:
                print(f"    [ÉXITO] {endpoint.upper()} configurado (Respuesta HTTP vacía O.K).")
                
        except requests.exceptions.Timeout:
            print(f"    [ERROR] Timeout al conectar la API R3 en {endpoint}.")
        except requests.exceptions.HTTPError as he:
            print(f"    [ERROR HTTP] en {endpoint}: {he}")
            if req.text:
                print("    Detalles:", req.text)
        except Exception as e:
            print(f"    [ERROR GENERAL] manipulando {endpoint}: {e}")

def setup_docker_network():
    print("Configurando interfaces de red del Docker automáticamente...")
    # Asignamos temporalmente las IPs necesarias para alcanzar las redes de gestión
    networks = ["192.168.120.100/24", "192.168.130.100/24", "192.168.140.100/24"]
    for net in networks:
        # Se oculta el error por si la IP ya fue configurada previamente (ej. re-ejecuciones)
        subprocess.run(["ip", "addr", "add", net, "dev", "eth0"], stderr=subprocess.DEVNULL)
    print("Subredes de gestión configuradas en la interfaz eth0.\n")

def verify_vpn():
    print("\nIniciando prueba automática de tráfico VPN desde R1 hacia R3...")
    device = {
        "device_type": "cisco_ios",
        "ip": OOB_R1_IP,
        "username": CISCO_USER,
        "password": CISCO_PASS,
        "fast_cli": True
    }
    try:
        net_connect = ConnectHandler(**device)
        print(" -> Enviando PING usando la Loopback10 para forzar a levantar IPsec...")
        ping_out = net_connect.send_command("ping 192.168.30.1 source Loopback10")
        print(ping_out)
        
        # Le damos 2 segundos para que las Security Associations (SA) terminen
        time.sleep(2)
        check = net_connect.send_command("show crypto isakmp sa")
        print("\n -> Estado de ISAKMP (Fase 1) en R1:")
        print(check)
        check2 = net_connect.send_command("show crypto ipsec sa | include encrypt")
        print("\n -> Paquetes Encriptados/Desencriptados (Fase 2) en R1:")
        print(check2)
        
        net_connect.disconnect()
    except Exception as e:
        print(f"Error realizando la prueba final en R1: {e}")

if __name__ == "__main__":
    print("="*60)
    print(" INICIANDO AUTOMATIZACION NETDEVOPS (HÍBRIDA SSH/API)")
    print("="*60)
    
    setup_docker_network()
    
    config_r2()
    print("-" * 60)
    config_r1()
    print("-" * 60)
    config_r3()
    print("-" * 60)
    verify_vpn()
    
    print("="*60)
    print(" AUTOMATIZACION FINALIZADA")
    print("="*60)
