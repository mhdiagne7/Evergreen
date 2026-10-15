"""Cas synthétiques réservés aux tests, jamais chargés par l’application."""

from core.data import load_csv_files

ROUTING_FILES = {
    "rooms.csv": b"""room_id,building,capacity,allowed_models
MRT 1140,MRT,20,Dell OptiPlex 7050|Dell OptiPlex 7060
MRT 120,MRT,25,Dell OptiPlex 7050
UCU 214,UCU,30,Dell OptiPlex 7050|Dell OptiPlex 7060
STE 1030,STE,20,Dell OptiPlex 7050
CBY 120,CBY,25,Dell OptiPlex 7060
CBY 210,CBY,20,HP EliteDesk 800
""",
    "inventory.csv": b"""room_id,model,quantity
MRT 1140,Dell OptiPlex 7050,10
MRT 1140,Dell OptiPlex 7060,2
MRT 120,Dell OptiPlex 7050,15
UCU 214,Dell OptiPlex 7060,12
STE 1030,Dell OptiPlex 7050,8
CBY 120,Dell OptiPlex 7060,18
CBY 210,HP EliteDesk 800,10
""",
    "connections.csv": b"""source,target,distance_m,distance_type
MRT 1140,MRT Hall,20,simulated
MRT 120,MRT Hall,30,simulated
MRT Hall,MRT Exit,30,simulated
MRT Exit,UCU Entry,100,simulated
UCU Entry,UCU 214,45,simulated
UCU Entry,STE Entry,300,simulated
STE Entry,STE 1030,40,simulated
STE Entry,CBY Entry,80,simulated
CBY Entry,CBY 120,25,simulated
CBY Entry,CBY 210,50,simulated
""",
}


def routing_data():
    return load_csv_files(ROUTING_FILES)
