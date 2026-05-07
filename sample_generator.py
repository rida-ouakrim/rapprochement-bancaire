import pandas as pd
import os

def generate_sample_data(output_dir="."):
    """
    Génère deux fichiers Excel d'exemple pour tester l'application de rapprochement bancaire.
    - Grand Livre (Comptabilité)
    - Relevé Bancaire
    """
    os.makedirs(output_dir, exist_ok=True)
    
    # 1. Grand Livre (Comptabilité)
    # Dans le Grand Livre, le Débit augmente l'actif (donc + pour les encaissements) et le Crédit diminue (- pour les décaissements)
    # Les colonnes types : Date, Référence, Libellé, Débit, Crédit
    compta_data = [
        {"Date": "2026-05-01", "Référence": "CHQ 88201", "Libellé": "Paiement Fournisseur Dupont", "Débit": 0.0, "Crédit": 1500.0},
        {"Date": "2026-05-02", "Référence": "CHQ 88202", "Libellé": "Fournitures bureau Sarl", "Débit": 0.0, "Crédit": 350.0}, # Écart Compta (Non encaissé en Banque)
        {"Date": "2026-05-04", "Référence": "VIR ASTON", "Libellé": "Virement client Aston", "Débit": 2400.0, "Crédit": 0.0}, # Match exact
        {"Date": "2026-05-05", "Référence": "", "Libellé": "Achat carburant gérant", "Débit": 0.0, "Crédit": 85.50}, # Match par montant & date (+3j)
        # Remise de chèques : 3 écritures compta distinctes qui font l'objet d'une seule remise globale en banque
        {"Date": "2026-05-06", "Référence": "REMISE 501", "Libellé": "Chèque Client Martin", "Débit": 500.0, "Crédit": 0.0},
        {"Date": "2026-05-06", "Référence": "REMISE 501", "Libellé": "Chèque Client Bernard", "Débit": 300.0, "Crédit": 0.0},
        {"Date": "2026-05-06", "Référence": "REMISE 501", "Libellé": "Chèque Client Petit", "Débit": 200.0, "Crédit": 0.0},
        {"Date": "2026-05-15", "Référence": "CHQ 88203", "Libellé": "Règlement Peinture Sarl", "Débit": 0.0, "Crédit": 1200.0}, # Match exact
    ]
    df_compta = pd.DataFrame(compta_data)
    df_compta["Date"] = pd.to_datetime(df_compta["Date"])
    
    # 2. Relevé Bancaire
    # Dans le relevé bancaire, un Crédit est un encaissement (+), et un Débit est un décaissement (-)
    # Les colonnes types : Date Valeur, Libellé Opération, Réf. Opération, Débit, Crédit
    banque_data = [
        {"Date Valeur": "2026-05-03", "Réf. Opération": "CHQ 88201", "Libellé Opération": "DEBIT CHEQUE 88201", "Débit": 1500.0, "Crédit": 0.0}, # Match exact CHQ 88201
        {"Date Valeur": "2026-05-05", "Réf. Opération": "VIR ASTON", "Libellé Opération": "VIR RECU ASTON", "Débit": 0.0, "Crédit": 2400.0}, # Match exact VIR ASTON
        {"Date Valeur": "2026-05-08", "Réf. Opération": "", "Libellé Opération": "PAIEMENT CB CARBURANT", "Débit": 85.50, "Crédit": 0.0}, # Match par montant (carburant)
        {"Date Valeur": "2026-05-07", "Réf. Opération": "REMISE 501", "Libellé Opération": "REMISE CHQ 501", "Débit": 0.0, "Crédit": 1000.0}, # Match somme (500+300+200)
        {"Date Valeur": "2026-05-10", "Réf. Opération": "", "Libellé Opération": "FRAIS TENUE COMPTE", "Débit": 12.50, "Crédit": 0.0}, # Écart Banque (Frais non saisis en compta)
        {"Date Valeur": "2026-05-18", "Réf. Opération": "CHQ 88203", "Libellé Opération": "DEBIT CHEQUE 88203", "Débit": 1200.0, "Crédit": 0.0}, # Match exact CHQ 88203
    ]
    df_banque = pd.DataFrame(banque_data)
    df_banque["Date Valeur"] = pd.to_datetime(df_banque["Date Valeur"])
    
    compta_path = os.path.join(output_dir, "grand_livre_compta_exemple.xlsx")
    banque_path = os.path.join(output_dir, "releve_bancaire_exemple.xlsx")
    
    df_compta.to_excel(compta_path, index=False)
    df_banque.to_excel(banque_path, index=False)
    
    return compta_path, banque_path

if __name__ == "__main__":
    c_p, b_p = generate_sample_data()
    print(f"Fichiers d'exemples créés avec succès :\n- {c_p}\n- {b_p}")
