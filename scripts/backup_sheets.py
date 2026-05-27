"""
Script para backup automático de Google Sheets.
Ejecutar diariamente con cron.
"""

import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import json
from pathlib import Path

def backup_sheets(sheet_id: str, credentials_path: str, backup_dir: str = "./backups"):
    """
    Realiza backup de una Google Sheet a JSON local.
    
    Args:
        sheet_id: ID de la Google Sheet
        credentials_path: Ruta a credenciales
        backup_dir: Directorio donde guardar backups
    """
    # Crear directorio si no existe
    Path(backup_dir).mkdir(exist_ok=True)
    
    # Autenticarse
    scopes = ['https://www.googleapis.com/auth/spreadsheets']
    credentials = Credentials.from_service_account_file(
        credentials_path, scopes=scopes
    )
    client = gspread.authorize(credentials)
    
    # Abrir sheet
    sheet = client.open_by_key(sheet_id)
    data = sheet.sheet1.get_all_records()
    
    # Guardar con timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = Path(backup_dir) / f"leads_backup_{timestamp}.json"
    
    with open(backup_file, "w") as f:
        json.dump(data, f, indent=2, default=str)
    
    print(f"✅ Backup guardado: {backup_file}")
    print(f"📊 Total de leads: {len(data)}")
    
    # Guardar también en CSV para fácil visualización
    import csv
    csv_file = Path(backup_dir) / f"leads_backup_{timestamp}.csv"
    
    if data:
        with open(csv_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=data[0].keys())
            writer.writeheader()
            writer.writerows(data)
    
    print(f"📄 CSV guardado: {csv_file}")

if __name__ == "__main__":
    from config.settings import Settings
    
    settings = Settings()
    backup_sheets(
        sheet_id=settings.google_sheet_id,
        credentials_path=settings.google_sheets_credentials_path
    )
