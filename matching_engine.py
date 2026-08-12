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

def extract_remise_ref(text):
    """
    Extrait spécifiquement le numéro d'une remise (ex: REMISE 000095175 -> 95175).
    """
    if pd.isna(text):
        return ""
    text = str(text).upper().replace('É', 'E').replace('È', 'E')
    
    # 1. Tenter un matching direct comme REMISE 12345
    match = re.search(r'REMISE\s*0*(\d+)', text)
    if match:
        return match.group(1)
        
    # 2. Si le mot "REMISE" est présent, chercher n'importe quelle séquence de 5 chiffres ou plus
    if "REMISE" in text:
        match = re.search(r'\b0*(\d{5,})\b', text)
        if match:
            return match.group(1)
            
    return ""

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
        # Chercher une référence numérique de 5 chiffres ou plus
        ref_match = re.search(r'\b0*(\d{5,})\b', text)
        if ref_match:
            extracted_ref = ref_match.group(1)
        else:
            # Fallback direct REMISE 123
            ref_match = re.search(r'REMISE\s*0*(\d+)', text)
            if ref_match:
                extracted_ref = ref_match.group(1)
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
    clean_df['_remise_ref'] = clean_df['_libelle'].apply(extract_remise_ref)
    
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
    
    group_tolerance = max(date_tolerance, 30)

    # -------------------------------------------------------------
    # ÉTAPE 1.5 : Rapprochement par Référence de Remise Commune (1-to-many, many-to-1)
    # -------------------------------------------------------------
    unmatched_c = c_df[~c_df['_row_id'].isin(matched_c_ids)]
    unmatched_b = b_df[~b_df['_row_id'].isin(matched_b_ids)]
    
    all_remise_refs = set(unmatched_c['_remise_ref'].dropna().unique()) | set(unmatched_b['_remise_ref'].dropna().unique())
    all_remise_refs.discard("")
    
    for ref in all_remise_refs:
        c_rows = unmatched_c[
            (unmatched_c['_remise_ref'] == ref) | 
            (unmatched_c['_ref'] == ref) |
            (unmatched_c['_ref_original'] == ref)
        ]
        b_rows = unmatched_b[
            (unmatched_b['_remise_ref'] == ref) | 
            (unmatched_b['_ref'] == ref) |
            (unmatched_b['_ref_original'] == ref)
        ]
        
        c_rows = c_rows[~c_rows['_row_id'].isin(matched_c_ids)]
        b_rows = b_rows[~b_rows['_row_id'].isin(matched_b_ids)]
        
        if not c_rows.empty and not b_rows.empty:
            c_sum = c_rows['_montant'].sum()
            b_sum = b_rows['_montant'].sum()
            
            if np.isclose(c_sum, b_sum, atol=0.01):
                for _, r in c_rows.iterrows():
                    matched_c_ids.add(r['_row_id'])
                for _, r in b_rows.iterrows():
                    matched_b_ids.add(r['_row_id'])
                
                for _, c_r in c_rows.iterrows():
                    for _, b_r in b_rows.iterrows():
                        matched_pairs.append({
                            'c_row_id': c_r['_row_id'],
                            'b_row_id': b_r['_row_id'],
                            'methode': f'Remise groupée par Réf ({ref})'
                        })

    # -------------------------------------------------------------
    # ÉTAPE 1.7 : Rapprochement de Remises par Somme de Référence Unique (1 côté avec Réf, 1 côté avec Somme Globale)
    # -------------------------------------------------------------
    unmatched_c = c_df[~c_df['_row_id'].isin(matched_c_ids)]
    unmatched_b = b_df[~b_df['_row_id'].isin(matched_b_ids)]
    
    # 1. Banque -> Compta (Plusieurs lignes Banque avec même Réf de Remise -> Une seule ligne globale Compta)
    b_grouped_refs = unmatched_b[unmatched_b['_remise_ref'] != ""]['_remise_ref'].unique()
    for ref in b_grouped_refs:
        b_rows = unmatched_b[unmatched_b['_remise_ref'] == ref]
        b_rows = b_rows[~b_rows['_row_id'].isin(matched_b_ids)]
        if b_rows.empty:
            continue
            
        b_sum = b_rows['_montant'].sum()
        c_candidates = unmatched_c[
            (np.isclose(unmatched_c['_montant'], b_sum, atol=0.01)) &
            (~unmatched_c['_row_id'].isin(matched_c_ids))
        ]
        
        if not c_candidates.empty:
            c_candidates = c_candidates.copy()
            b_dates = b_rows['_date'].dropna()
            if b_dates.empty:
                continue
            b_avg_date = b_dates.min()
            c_candidates['date_diff_days'] = (c_candidates['_date'] - b_avg_date).dt.days.abs()
            valid_c = c_candidates[c_candidates['date_diff_days'] <= group_tolerance]
            
            if not valid_c.empty:
                best_c = valid_c.sort_values('date_diff_days').iloc[0]
                c_id = best_c['_row_id']
                
                matched_c_ids.add(c_id)
                for _, b_r in b_rows.iterrows():
                    matched_b_ids.add(b_r['_row_id'])
                    matched_pairs.append({
                        'c_row_id': c_id,
                        'b_row_id': b_r['_row_id'],
                        'methode': f'Remise groupée Banque Réf ({ref})'
                    })

    # 2. Compta -> Banque (Plusieurs lignes Compta avec même Réf de Remise -> Une seule ligne globale Banque)
    unmatched_c = c_df[~c_df['_row_id'].isin(matched_c_ids)]
    unmatched_b = b_df[~b_df['_row_id'].isin(matched_b_ids)]
    
    c_grouped_refs = unmatched_c[unmatched_c['_remise_ref'] != ""]['_remise_ref'].unique()
    for ref in c_grouped_refs:
        c_rows = unmatched_c[unmatched_c['_remise_ref'] == ref]
        c_rows = c_rows[~c_rows['_row_id'].isin(matched_c_ids)]
        if c_rows.empty:
            continue
            
        c_sum = c_rows['_montant'].sum()
        b_candidates = unmatched_b[
            (np.isclose(unmatched_b['_montant'], c_sum, atol=0.01)) &
            (~unmatched_b['_row_id'].isin(matched_b_ids))
        ]
        
        if not b_candidates.empty:
            b_candidates = b_candidates.copy()
            c_dates = c_rows['_date'].dropna()
            if c_dates.empty:
                continue
            c_avg_date = c_dates.min()
            b_candidates['date_diff_days'] = (b_candidates['_date'] - c_avg_date).dt.days.abs()
            valid_b = b_candidates[b_candidates['date_diff_days'] <= group_tolerance]
            
            if not valid_b.empty:
                best_b = valid_b.sort_values('date_diff_days').iloc[0]
                b_id = best_b['_row_id']
                
                matched_b_ids.add(b_id)
                for _, c_r in c_rows.iterrows():
                    matched_c_ids.add(c_r['_row_id'])
                    matched_pairs.append({
                        'c_row_id': c_r['_row_id'],
                        'b_row_id': b_id,
                        'methode': f'Remise groupée Compta Réf ({ref})'
                    })

    # -------------------------------------------------------------
    # ÉTAPE 1.8 : Rapprochement élargi Somme Banque (même REMISE) -> Compta (sans restriction de type)
    # Cas: plusieurs lignes banque avec même n° REMISE, leur somme = une ligne compta
    # Plus large que 1.7 : pas de contrainte de type d'opération côté compta, tolérance de date étendue
    # -------------------------------------------------------------
    unmatched_c = c_df[~c_df['_row_id'].isin(matched_c_ids)]
    unmatched_b = b_df[~b_df['_row_id'].isin(matched_b_ids)]
    
    extended_tolerance = max(group_tolerance, 90)
    
    # 1. Banque -> Compta (Plusieurs lignes Banque même Réf REMISE -> Une ligne Compta quelconque)
    b_grouped_refs_ext = unmatched_b[unmatched_b['_remise_ref'] != ""]['_remise_ref'].unique()
    for ref in b_grouped_refs_ext:
        b_rows = unmatched_b[
            (unmatched_b['_remise_ref'] == ref) &
            (~unmatched_b['_row_id'].isin(matched_b_ids))
        ]
        if b_rows.empty or len(b_rows) < 2:
            continue
            
        b_sum = b_rows['_montant'].sum()
        if np.isclose(b_sum, 0, atol=0.01):
            continue
        
        # Chercher TOUTE ligne compta non matchée avec ce montant (pas de filtre de type)
        c_candidates = unmatched_c[
            (np.isclose(unmatched_c['_montant'], b_sum, atol=0.01)) &
            (~unmatched_c['_row_id'].isin(matched_c_ids))
        ]
        
        if not c_candidates.empty:
            c_candidates = c_candidates.copy()
            b_dates = b_rows['_date'].dropna()
            if b_dates.empty:
                # Même sans date, si le montant correspond exactement, on matche
                best_c = c_candidates.iloc[0]
            else:
                b_min_date = b_dates.min()
                c_candidates['date_diff_days'] = (c_candidates['_date'] - b_min_date).dt.days.abs()
                valid_c = c_candidates[c_candidates['date_diff_days'] <= extended_tolerance]
                if valid_c.empty:
                    continue
                best_c = valid_c.sort_values('date_diff_days').iloc[0]
            
            c_id = best_c['_row_id']
            matched_c_ids.add(c_id)
            for _, b_r in b_rows.iterrows():
                matched_b_ids.add(b_r['_row_id'])
                matched_pairs.append({
                    'c_row_id': c_id,
                    'b_row_id': b_r['_row_id'],
                    'methode': f'Somme Remises Banque ({ref}) → Compta'
                })
    
    # 2. Compta -> Banque (Plusieurs lignes Compta même Réf REMISE -> Une ligne Banque quelconque)
    unmatched_c = c_df[~c_df['_row_id'].isin(matched_c_ids)]
    unmatched_b = b_df[~b_df['_row_id'].isin(matched_b_ids)]
    
    c_grouped_refs_ext = unmatched_c[unmatched_c['_remise_ref'] != ""]['_remise_ref'].unique()
    for ref in c_grouped_refs_ext:
        c_rows = unmatched_c[
            (unmatched_c['_remise_ref'] == ref) &
            (~unmatched_c['_row_id'].isin(matched_c_ids))
        ]
        if c_rows.empty or len(c_rows) < 2:
            continue
            
        c_sum = c_rows['_montant'].sum()
        if np.isclose(c_sum, 0, atol=0.01):
            continue
        
        b_candidates = unmatched_b[
            (np.isclose(unmatched_b['_montant'], c_sum, atol=0.01)) &
            (~unmatched_b['_row_id'].isin(matched_b_ids))
        ]
        
        if not b_candidates.empty:
            b_candidates = b_candidates.copy()
            c_dates = c_rows['_date'].dropna()
            if c_dates.empty:
                best_b = b_candidates.iloc[0]
            else:
                c_min_date = c_dates.min()
                b_candidates['date_diff_days'] = (b_candidates['_date'] - c_min_date).dt.days.abs()
                valid_b = b_candidates[b_candidates['date_diff_days'] <= extended_tolerance]
                if valid_b.empty:
                    continue
                best_b = valid_b.sort_values('date_diff_days').iloc[0]
            
            b_id = best_b['_row_id']
            matched_b_ids.add(b_id)
            for _, c_r in c_rows.iterrows():
                matched_c_ids.add(c_r['_row_id'])
                matched_pairs.append({
                    'c_row_id': c_r['_row_id'],
                    'b_row_id': b_id,
                    'methode': f'Somme Remises Compta ({ref}) → Banque'
                })

    # -------------------------------------------------------------
    # ÉTAPE 1.9 : Rapprochement par somme de sous-ensemble banque (même REMISE) → ligne compta
    # Cas: on cherche des combinaisons de lignes banque partageant le même n° REMISE
    # dont la somme correspond à une ligne compta, en validant avec les derniers chiffres identiques
    # -------------------------------------------------------------
    unmatched_c = c_df[~c_df['_row_id'].isin(matched_c_ids)]
    unmatched_b = b_df[~b_df['_row_id'].isin(matched_b_ids)]
    
    # Grouper les lignes banque non matchées par leur référence de remise
    b_with_remise = unmatched_b[
        (unmatched_b['_remise_ref'] != "") & 
        (~unmatched_b['_row_id'].isin(matched_b_ids))
    ]
    
    if not b_with_remise.empty:
        for remise_ref, b_group in b_with_remise.groupby('_remise_ref'):
            if len(b_group) < 2:
                continue
            
            b_group_sum = b_group['_montant'].sum()
            if np.isclose(b_group_sum, 0, atol=0.01):
                continue
            
            # Chercher dans les écarts compta une ligne avec ce montant exact
            for _, c_row in unmatched_c.iterrows():
                c_id = c_row['_row_id']
                if c_id in matched_c_ids:
                    continue
                    
                c_montant = c_row['_montant']
                
                if np.isclose(c_montant, b_group_sum, atol=0.01):
                    # Validation supplémentaire : vérifier si des chiffres du n° de remise
                    # apparaissent dans la référence ou le libellé compta
                    c_libelle = str(c_row.get('_libelle', '')).upper()
                    c_ref = str(c_row.get('_ref', ''))
                    c_ref_orig = str(c_row.get('_ref_original', ''))
                    
                    # Extraire les derniers chiffres significatifs du n° de remise
                    remise_digits = str(remise_ref).lstrip('0')
                    last_digits = remise_digits[-4:] if len(remise_digits) >= 4 else remise_digits
                    
                    # Vérifier si les derniers chiffres du numéro de remise apparaissent
                    # dans les infos compta (libellé, ref) - ça renforce la confiance
                    has_digit_match = (
                        last_digits in c_libelle or 
                        last_digits in c_ref or 
                        last_digits in c_ref_orig or
                        remise_digits in c_libelle or
                        remise_digits in c_ref or
                        remise_digits in c_ref_orig
                    )
                    
                    # On matche si : montant identique ET (chiffres communs OU type REMISE côté compta)
                    is_remise_type = c_row.get('_op_type', '') in ('REMISE', 'CHEQUE', 'REGLEMENT', '')
                    
                    if has_digit_match or is_remise_type:
                        matched_c_ids.add(c_id)
                        for _, b_r in b_group.iterrows():
                            matched_b_ids.add(b_r['_row_id'])
                            matched_pairs.append({
                                'c_row_id': c_id,
                                'b_row_id': b_r['_row_id'],
                                'methode': f'Somme sous-groupe Remise ({remise_ref}) = Compta'
                            })
                        break  # On a trouvé le match, passer au groupe suivant

    # Sens inverse : grouper les lignes compta non matchées par REMISE ref -> chercher somme en banque
    unmatched_c = c_df[~c_df['_row_id'].isin(matched_c_ids)]
    unmatched_b = b_df[~b_df['_row_id'].isin(matched_b_ids)]
    
    c_with_remise = unmatched_c[
        (unmatched_c['_remise_ref'] != "") & 
        (~unmatched_c['_row_id'].isin(matched_c_ids))
    ]
    
    if not c_with_remise.empty:
        for remise_ref, c_group in c_with_remise.groupby('_remise_ref'):
            if len(c_group) < 2:
                continue
            
            c_group_sum = c_group['_montant'].sum()
            if np.isclose(c_group_sum, 0, atol=0.01):
                continue
            
            for _, b_row in unmatched_b.iterrows():
                b_id = b_row['_row_id']
                if b_id in matched_b_ids:
                    continue
                    
                b_montant = b_row['_montant']
                
                if np.isclose(b_montant, c_group_sum, atol=0.01):
                    b_libelle = str(b_row.get('_libelle', '')).upper()
                    b_ref = str(b_row.get('_ref', ''))
                    b_ref_orig = str(b_row.get('_ref_original', ''))
                    
                    remise_digits = str(remise_ref).lstrip('0')
                    last_digits = remise_digits[-4:] if len(remise_digits) >= 4 else remise_digits
                    
                    has_digit_match = (
                        last_digits in b_libelle or 
                        last_digits in b_ref or 
                        last_digits in b_ref_orig or
                        remise_digits in b_libelle or
                        remise_digits in b_ref or
                        remise_digits in b_ref_orig
                    )
                    
                    is_remise_type = b_row.get('_op_type', '') in ('REMISE', 'CHEQUE', 'REGLEMENT', '')
                    
                    if has_digit_match or is_remise_type:
                        matched_b_ids.add(b_id)
                        for _, c_r in c_group.iterrows():
                            matched_c_ids.add(c_r['_row_id'])
                            matched_pairs.append({
                                'c_row_id': c_r['_row_id'],
                                'b_row_id': b_id,
                                'methode': f'Somme sous-groupe Remise Compta ({remise_ref}) = Banque'
                            })
                        break

    # -------------------------------------------------------------
    # ÉTAPE 1 : Rapprochement Exact par Référence & Montant
    # -------------------------------------------------------------
    for _, c_row in c_df.iterrows():
        c_id = c_row['_row_id']
        if c_id in matched_c_ids:
            continue
        c_ref = c_row['_ref']
        c_montant = c_row['_montant']
        
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
    # ÉTAPE 2 : Rapprochement par Remise (Somme Compta = Ligne Banque, ou inversement)
    # -------------------------------------------------------------
    unmatched_c = c_df[~c_df['_row_id'].isin(matched_c_ids)]
    unmatched_b = b_df[~b_df['_row_id'].isin(matched_b_ids)]
    
    # Trouver les lignes de banque "REMISE" (Many Compta -> One Banque)
    b_remises = unmatched_b[unmatched_b['_op_type'] == "REMISE"]
    for _, b_row in b_remises.iterrows():
        b_montant = b_row['_montant']
        b_date = b_row['_date']
        b_id = b_row['_row_id']
        
        if pd.isna(b_date):
            continue
            
        c_candidates = unmatched_c[
            (unmatched_c['_op_type'].isin(['CHEQUE', 'REMISE'])) &
            (~unmatched_c['_row_id'].isin(matched_c_ids))
        ]
        c_candidates = c_candidates.copy()
        c_candidates['date_diff_days'] = (c_candidates['_date'] - b_date).dt.days.abs()
        c_candidates = c_candidates[c_candidates['date_diff_days'] <= date_tolerance]
        
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

    # Trouver les lignes de compta "REMISE" (One Compta -> Many Banque)
    unmatched_c = c_df[~c_df['_row_id'].isin(matched_c_ids)]
    unmatched_b = b_df[~b_df['_row_id'].isin(matched_b_ids)]
    c_remises = unmatched_c[unmatched_c['_op_type'] == "REMISE"]
    for _, c_row in c_remises.iterrows():
        c_montant = c_row['_montant']
        c_date = c_row['_date']
        c_id = c_row['_row_id']
        
        if pd.isna(c_date):
            continue
            
        b_candidates = unmatched_b[
            (unmatched_b['_op_type'].isin(['CHEQUE', 'REMISE'])) &
            (~unmatched_b['_row_id'].isin(matched_b_ids))
        ]
        b_candidates = b_candidates.copy()
        b_candidates['date_diff_days'] = (b_candidates['_date'] - c_date).dt.days.abs()
        b_candidates = b_candidates[b_candidates['date_diff_days'] <= date_tolerance]
        
        if np.isclose(b_candidates['_montant'].sum(), c_montant, atol=0.01):
            matched_c_ids.add(c_id)
            for _, b_row in b_candidates.iterrows():
                matched_b_ids.add(b_row['_row_id'])
                matched_pairs.append({
                    'c_row_id': c_id,
                    'b_row_id': b_row['_row_id'],
                    'methode': 'Remise groupée inversée par date'
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
