import pandas as pd
import numpy as np
import re

def clean_reference(ref):
    """
    Nettoie une référence pour optimiser le matching.
    """
    if pd.isna(ref) or str(ref).strip() == "" or str(ref).lower() == "nan":
        return ""
    ref_str = str(ref).strip().upper()
    if ref_str.isdigit():
        return str(int(ref_str))
    return ref_str

def extract_features(text):
    """
    Extrait les informations pertinentes d'un libellé (numéro de chèque, type d'opération).
    """
    if pd.isna(text):
        return "", ""
        
    text = str(text).upper().replace('É', 'E').replace('È', 'E')
    extracted_ref = ""
    op_type = ""
    
    # 1. Chèques
    cheque_match = re.search(r'(?:CHQ|CHEQUE|CHÈQUE)\s*(?:N|N°)?\s*[:.-]?\s*0*(\d+)', text)
    if cheque_match:
        extracted_ref = cheque_match.group(1)
        op_type = "CHEQUE"
        return extracted_ref, op_type
        
    # 2. LCN / Effets
    lcn_match = re.search(r'(?:LCN|EFFET)\s*(?:N|N°)?\s*[:.-]?\s*0*(\d+)', text)
    if lcn_match:
        extracted_ref = lcn_match.group(1)
        op_type = "LCN"
        return extracted_ref, op_type
        
    # 3. Virements
    if re.search(r'\b(?:VIRT|VIREMENT|VIR)\b', text):
        op_type = "VIREMENT"
        ref_match = re.search(r'\b(15TRF\d+|\d{6,})\b', text)
        if ref_match:
            extracted_ref = ref_match.group(1)
        return extracted_ref, op_type
        
    # 4. Remises
    if "REMISE" in text:
        op_type = "REMISE"
        return extracted_ref, op_type
        
    # 5. Frais / Agio
    if "FRAIS" in text or "AGIO" in text or "COMMISSION" in text or "COM ENCAISS" in text or "TVA" in text or "DEC TIMBRE" in text:
        op_type = "FRAIS"
        return extracted_ref, op_type

    # Fallback ref numérique
    ref_match = re.search(r'\b0*(\d{5,})\b', text)
    if ref_match:
        extracted_ref = ref_match.group(1)
        
    return extracted_ref, op_type

def prepare_data(df, date_col, ref_col, libelle_col, debit_col=None, credit_col=None, montant_col=None, is_compta=True):
    clean_df = df.copy()
    clean_df['_row_id'] = range(len(clean_df))
    clean_df['_date'] = pd.to_datetime(clean_df[date_col], errors='coerce', dayfirst=True)
    
    if ref_col and ref_col in clean_df.columns:
        clean_df['_ref_original'] = clean_df[ref_col].apply(clean_reference)
    else:
        clean_df['_ref_original'] = ""
        
    if libelle_col and libelle_col in clean_df.columns:
        clean_df['_libelle'] = clean_df[libelle_col].astype(str).fillna("")
    else:
        clean_df['_libelle'] = ""
        
    # Extract features
    features = clean_df['_libelle'].apply(extract_features)
    clean_df['_extracted_ref'] = features.apply(lambda x: x[0])
    clean_df['_op_type'] = features.apply(lambda x: x[1])
    
    # Priority to extracted ref, fallback to original ref
    clean_df['_ref'] = clean_df.apply(lambda row: row['_extracted_ref'] if row['_extracted_ref'] != "" else row['_ref_original'], axis=1)

    if montant_col and montant_col in clean_df.columns:
        clean_df['_montant'] = pd.to_numeric(clean_df[montant_col], errors='coerce').fillna(0.0)
    elif debit_col and debit_col in clean_df.columns and credit_col and credit_col in clean_df.columns:
        debit = pd.to_numeric(clean_df[debit_col], errors='coerce').fillna(0.0)
        credit = pd.to_numeric(clean_df[credit_col], errors='coerce').fillna(0.0)
        if is_compta:
            clean_df['_montant'] = debit - credit
        else:
            clean_df['_montant'] = credit - debit
    else:
        clean_df['_montant'] = 0.0
        
    return clean_df

def reconcile_dfs(df_compta_raw, df_banque_raw, compta_mapping, banque_mapping, date_tolerance=10):
    c_df = prepare_data(
        df_compta_raw,
        date_col=compta_mapping['date'],
        ref_col=compta_mapping.get('ref'),
        libelle_col=compta_mapping.get('libelle'),
        debit_col=compta_mapping.get('debit'),
        credit_col=compta_mapping.get('credit'),
        montant_col=compta_mapping.get('montant'),
        is_compta=True
    )
    
    b_df = prepare_data(
        df_banque_raw,
        date_col=banque_mapping['date'],
        ref_col=banque_mapping.get('ref'),
        libelle_col=banque_mapping.get('libelle'),
        debit_col=banque_mapping.get('debit'),
        credit_col=banque_mapping.get('credit'),
        montant_col=banque_mapping.get('montant'),
        is_compta=False
    )
    
    matched_pairs = []
    matched_c_ids = set()
    matched_b_ids = set()
    
    # -------------------------------------------------------------
    # ÉTAPE 1 : Rapprochement Exact par Référence & Montant
    # -------------------------------------------------------------
    for _, c_row in c_df.iterrows():
        c_ref = c_row['_ref']
        c_montant = c_row['_montant']
        c_id = c_row['_row_id']
        
        if c_ref == "":
            continue
            
        b_candidates = b_df[
            (b_df['_ref'] == c_ref) & 
            (np.isclose(b_df['_montant'], c_montant, atol=0.01)) & 
            (~b_df['_row_id'].isin(matched_b_ids))
        ]
        
        if not b_candidates.empty:
            b_candidates = b_candidates.copy()
            b_candidates['date_diff'] = (b_candidates['_date'] - c_row['_date']).abs()
            best_b_row = b_candidates.sort_values('date_diff').iloc[0]
            b_id = best_b_row['_row_id']
            
            matched_c_ids.add(c_id)
            matched_b_ids.add(b_id)
            matched_pairs.append({
                'c_row_id': c_id,
                'b_row_id': b_id,
                'methode': f'Référence exacte ({c_row["_op_type"]}) & Montant'
            })

    # -------------------------------------------------------------
    # ÉTAPE 2 : Rapprochement par Remise (Somme Compta = Ligne Banque)
    # -------------------------------------------------------------
    unmatched_c = c_df[~c_df['_row_id'].isin(matched_c_ids)]
    unmatched_b = b_df[~b_df['_row_id'].isin(matched_b_ids)]
    
    # Trouver les lignes de banque "REMISE"
    b_remises = unmatched_b[unmatched_b['_op_type'] == "REMISE"]
    for _, b_row in b_remises.iterrows():
        b_montant = b_row['_montant']
        b_date = b_row['_date']
        b_id = b_row['_row_id']
        
        # On cherche des combinaisons de chèques ou remises en compta à la même date
        if pd.isna(b_date):
            continue
            
        c_candidates = unmatched_c[
            (unmatched_c['_op_type'].isin(['CHEQUE', 'REMISE'])) &
            (~unmatched_c['_row_id'].isin(matched_c_ids))
        ]
        c_candidates = c_candidates.copy()
        c_candidates['date_diff_days'] = (c_candidates['_date'] - b_date).dt.days.abs()
        c_candidates = c_candidates[c_candidates['date_diff_days'] <= date_tolerance]
        
        # Si la somme totale correspond (cas simple où il n'y a qu'une remise ce jour-là)
        if np.isclose(c_candidates['_montant'].sum(), b_montant, atol=0.01):
            matched_b_ids.add(b_id)
            for _, c_row in c_candidates.iterrows():
                matched_c_ids.add(c_row['_row_id'])
                matched_pairs.append({
                    'c_row_id': c_row['_row_id'],
                    'b_row_id': b_id,
                    'methode': 'Remise groupée par date'
                })
        else:
            # Essayer de trouver une seule ligne compta "REMISE" du même montant
            c_single = c_candidates[np.isclose(c_candidates['_montant'], b_montant, atol=0.01)]
            if not c_single.empty:
                best_c = c_single.sort_values('date_diff_days').iloc[0]
                matched_b_ids.add(b_id)
                matched_c_ids.add(best_c['_row_id'])
                matched_pairs.append({
                    'c_row_id': best_c['_row_id'],
                    'b_row_id': b_id,
                    'methode': 'Remise unitaire par montant'
                })
                
    # -------------------------------------------------------------
    # ÉTAPE 3 : Rapprochement par Montant & Type d'Opération
    # -------------------------------------------------------------
    unmatched_c = c_df[~c_df['_row_id'].isin(matched_c_ids)]
    unmatched_b = b_df[~b_df['_row_id'].isin(matched_b_ids)]
    
    for _, c_row in unmatched_c.iterrows():
        c_montant = c_row['_montant']
        c_date = c_row['_date']
        c_op_type = c_row['_op_type']
        c_id = c_row['_row_id']
        
        if pd.isna(c_date) or c_op_type == "":
            continue
            
        b_candidates = unmatched_b[
            (unmatched_b['_op_type'] == c_op_type) &
            (np.isclose(unmatched_b['_montant'], c_montant, atol=0.01)) & 
            (~unmatched_b['_row_id'].isin(matched_b_ids))
        ]
        
        if not b_candidates.empty:
            b_candidates = b_candidates.copy()
            b_candidates['date_diff_days'] = (b_candidates['_date'] - c_date).dt.days.abs()
            valid_candidates = b_candidates[b_candidates['date_diff_days'] <= date_tolerance]
            
            if not valid_candidates.empty:
                best_b_row = valid_candidates.sort_values('date_diff_days').iloc[0]
                b_id = best_b_row['_row_id']
                
                matched_c_ids.add(c_id)
                matched_b_ids.add(b_id)
                matched_pairs.append({
                    'c_row_id': c_id,
                    'b_row_id': b_id,
                    'methode': f'Montant & Type ({c_op_type})'
                })
                
    # -------------------------------------------------------------
    # ÉTAPE 4 : Fallback Montant identique & Proximité
    # -------------------------------------------------------------
    unmatched_c = c_df[~c_df['_row_id'].isin(matched_c_ids)]
    unmatched_b = b_df[~b_df['_row_id'].isin(matched_b_ids)]
    
    for _, c_row in unmatched_c.iterrows():
        c_montant = c_row['_montant']
        c_date = c_row['_date']
        c_id = c_row['_row_id']
        
        if pd.isna(c_date):
            continue
            
        b_candidates = unmatched_b[
            (np.isclose(unmatched_b['_montant'], c_montant, atol=0.01)) & 
            (~unmatched_b['_row_id'].isin(matched_b_ids))
        ]
        
        if not b_candidates.empty:
            b_candidates = b_candidates.copy()
            b_candidates['date_diff_days'] = (b_candidates['_date'] - c_date).dt.days.abs()
            valid_candidates = b_candidates[b_candidates['date_diff_days'] <= date_tolerance]
            
            if not valid_candidates.empty:
                best_b_row = valid_candidates.sort_values('date_diff_days').iloc[0]
                b_id = best_b_row['_row_id']
                
                matched_c_ids.add(c_id)
                matched_b_ids.add(b_id)
                matched_pairs.append({
                    'c_row_id': c_id,
                    'b_row_id': b_id,
                    'methode': f'Montant identique (+/- {best_b_row["date_diff_days"]} jours)'
                })

    # -------------------------------------------------------------
    # ÉTAPE 5 : Construction des rapports finaux
    # -------------------------------------------------------------
    df_matches = []
    for pair in matched_pairs:
        c_row = c_df[c_df['_row_id'] == pair['c_row_id']].iloc[0]
        b_row = b_df[b_df['_row_id'] == pair['b_row_id']].iloc[0]
        
        match_dict = {
            'Méthode Rapprochement': pair['methode'],
            'Date Compta': c_row['_date'].strftime('%Y-%m-%d') if pd.notna(c_row['_date']) else "",
            'Réf Compta Extr.': c_row['_ref'],
            'Libellé Compta': c_row['_libelle'],
            'Montant Compta': c_row['_montant'],
            'Date Banque': b_row['_date'].strftime('%Y-%m-%d') if pd.notna(b_row['_date']) else "",
            'Réf Banque Extr.': b_row['_ref'],
            'Libellé Banque': b_row['_libelle'],
            'Montant Banque': b_row['_montant'],
        }
        df_matches.append(match_dict)
        
    df_table_a = pd.DataFrame(df_matches) if df_matches else pd.DataFrame(columns=[
        'Méthode Rapprochement', 'Date Compta', 'Réf Compta Extr.', 'Libellé Compta', 'Montant Compta',
        'Date Banque', 'Réf Banque Extr.', 'Libellé Banque', 'Montant Banque'
    ])
    
    df_table_b_raw = df_compta_raw[~c_df['_row_id'].isin(matched_c_ids)].copy()
    c_unmatched_std = c_df[~c_df['_row_id'].isin(matched_c_ids)]
    df_table_b_raw['Montant Standardisé'] = c_unmatched_std['_montant']
    
    df_table_c_raw = df_banque_raw[~b_df['_row_id'].isin(matched_b_ids)].copy()
    b_unmatched_std = b_df[~b_df['_row_id'].isin(matched_b_ids)]
    df_table_c_raw['Montant Standardisé'] = b_unmatched_std['_montant']
    
    return df_table_a, df_table_b_raw, df_table_c_raw
