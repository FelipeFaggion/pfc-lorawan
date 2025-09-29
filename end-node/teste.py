import machine

def get_device_eui():
    """
    Retrieves the unique board ID and constructs a Device EUI.
    """
    unique_id = machine.unique_id() # Retorna bytes (ex: b'\x00\x00\x00\x00\x00\x00\x00\x00')

    unique_id_hex = unique_id.hex() # Ex: '0000000000000000'
    

    device_eui = unique_id_hex
    
    return device_eui

# Get the Device EUI
device_eui = get_device_eui()
print(f"Device EUI: {device_eui}") # F-strings são suportadas em MicroPython recente