import os
import json
import pandas as pd
import vertexai
from vertexai.generative_models import GenerativeModel, Part

def extract_bank_statement_pdf(pdf_bytes):
    """
    Appelle Gemini 2.5 Flash sur Vertex AI pour extraire toutes les transactions d'un relevé bancaire PDF.
    """
    import streamlit as st
    
    creds_info = None
    
    # 1. Vérifier si les credentials sont définis dans les secrets Streamlit (déploiement en ligne)
    if "gcp_service_account" in st.secrets:
        creds_info = dict(st.secrets["gcp_service_account"])
    elif "GOOGLE_APPLICATION_CREDENTIALS_JSON" in st.secrets:
        try:
            creds_info = json.loads(st.secrets["GOOGLE_APPLICATION_CREDENTIALS_JSON"])
        except Exception:
            pass
            
    # 2. Si non définis dans les secrets, chercher le fichier local
    if not creds_info:
        creds_path = r"C:\Users\RIDA OUAKRIM\Desktop\rida\vertex_credentials.json"
        if os.path.exists(creds_path):
            with open(creds_path, "r") as f:
                creds_info = json.load(f)
        else:
            local_creds = "vertex_credentials.json"
            if os.path.exists(local_creds):
                with open(local_creds, "r") as f:
                    creds_info = json.load(f)
                    
    if not creds_info:
        raise FileNotFoundError(
            "Identifiants Google Cloud introuvables. Veuillez configurer le fichier "
            "vertex_credentials.json ou ajouter 'gcp_service_account' dans les secrets Streamlit."
        )

    # Écrire temporairement les credentials dans un fichier temporaire caché exclu de Git
    temp_creds_path = os.path.join(os.getcwd(), ".tmp_credentials.json")
    with open(temp_creds_path, "w") as f:
        json.dump(creds_info, f)
        
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = temp_creds_path
    project_id = creds_info.get("quota_project_id", "chrome-backbone-496013-p4")
    
    # Initialiser Vertex AI
    vertexai.init(project=project_id, location="us-central1")
    model = GenerativeModel("gemini-2.5-flash")
    
    # Préparer le document PDF
    pdf_part = Part.from_data(data=pdf_bytes, mime_type="application/pdf")
    
    prompt = """
Vous êtes un expert comptable et analyste de données financières. Votre tâche est d'analyser le relevé bancaire PDF ci-joint (Attijariwafa bank) et d'extraire TOUTES les transactions sans aucune omission.

Pour chaque transaction, vous devez extraire les champs suivants:
- date: Date de l'opération au format DD/MM/YYYY.
- libelle: Libellé complet de l'opération (en nettoyant les espaces inutiles).
- date_valeur: Date de valeur au format DD/MM/YYYY.
- debit: Montant au débit (nombre positif) s'il s'agit d'un retrait/débit, sinon null.
- credit: Montant au crédit (nombre positif) s'il s'agit d'un dépôt/crédit, sinon null.

Consignes importantes:
1. Le relevé contient plusieurs pages. Parcourez chaque page avec soin. Ne sautez aucune transaction.
2. Formatez les nombres sous forme de décimaux en éliminant les espaces (ex: "9 892 000,00" -> 9892000.00).
3. Soyez très attentif à distinguer le débit du crédit. Dans le relevé d'Attijariwafa bank, les débits sont les retraits/décaissements et les crédits sont les dépôts/encaissements.
4. Formatez la réponse uniquement sous forme d'un objet JSON avec une unique clé "transactions" contenant une liste d'objets JSON. Ne mettez aucun texte d'introduction ni de conclusion, et pas de bloc de code markdown. La sortie doit être directement un JSON valide.
"""
    
    response = model.generate_content(
        [pdf_part, prompt],
        generation_config={
            "response_mime_type": "application/json",
            "temperature": 0.0
        }
    )
    
    raw_text = response.text.strip()
    # Nettoyer d'éventuels tags markdown si le modèle en a rajouté malgré le format de sortie JSON
    if raw_text.startswith("```json"):
        raw_text = raw_text.replace("```json", "", 1)
    if raw_text.endswith("```"):
        raw_text = raw_text.rsplit("```", 1)[0]
    raw_text = raw_text.strip()
    
    result = json.loads(raw_text)
    transactions = result.get("transactions", [])
    
    df = pd.DataFrame(transactions)
    
    # Assurer la présence et l'ordre des colonnes standards
    standard_columns = ['date', 'libelle', 'date_valeur', 'debit', 'credit']
    for col in standard_columns:
        if col not in df.columns:
            df[col] = None
            
    df = df[standard_columns]
    
    # Convertir debit et credit en numériques
    df['debit'] = pd.to_numeric(df['debit'], errors='coerce')
    df['credit'] = pd.to_numeric(df['credit'], errors='coerce')
    
    return df
