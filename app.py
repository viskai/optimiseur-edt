# app.py
import streamlit as st
import pandas as pd
import csv
from io import StringIO
from math import ceil
from collections import defaultdict, Counter
import itertools

# --- Fonctions de l'algorithme (identiques à avant) ---
# (On ne les affiche pas ici pour la lisibilité, mais elles sont dans le code complet ci-dessous)
# ... parse_student_data, get_base_specialty, step1_preprocess_and_create_groups, etc. ...

def get_base_specialty(group_name):
    """Extrait le nom de la spécialité de base d'un nom de groupe."""
    return group_name.split(' G')[0]

def parse_student_data(file_content):
    student_choices = {}
    f = StringIO(file_content)
    try:
        # Tente de détecter si un point-virgule est utilisé comme délimiteur
        sniffer = csv.Sniffer()
        dialect = sniffer.sniff(f.read(1024), delimiters=',;')
        f.seek(0)
        reader = csv.reader(f, dialect)
    except csv.Error:
        # Si la détection échoue, revient au délimiteur virgule par défaut
        f.seek(0)
        reader = csv.reader(f)
        
    header = next(reader)
    for row in reader:
        if not row: continue
        student_name = row[0].strip()
        specialties = sorted([spec.strip() for spec in row[1:] if spec.strip()])
        if len(specialties) == 3:
            student_choices[student_name] = specialties
    return student_choices

def step1_preprocess_and_create_groups(student_choices, max_capacity):
    all_chosen_specialties = [spec for choices in student_choices.values() for spec in choices]
    specialty_counts = Counter(all_chosen_specialties)
    specialty_groups = []
    log_messages = []

    for spec, count in sorted(specialty_counts.items()):
        num_groups = ceil(count / max_capacity)
        if num_groups > 1:
            log_messages.append(f"INFO : La spécialité '{spec}' ({count} élèves) est dédoublée en {num_groups} groupes.")
        for i in range(1, num_groups + 1):
            specialty_groups.append(f"{spec} G{i}")
            
    return specialty_groups, specialty_counts, log_messages

def step2_build_conflict_graph(specialty_groups, student_choices):
    conflicts = defaultdict(set)
    for student, choices in student_choices.items():
        for spec1, spec2 in itertools.combinations(choices, 2):
            groups1 = [g for g in specialty_groups if get_base_specialty(g) == spec1]
            groups2 = [g for g in specialty_groups if get_base_specialty(g) == spec2]
            for g1 in groups1:
                for g2 in groups2:
                    conflicts[g1].add(g2)
                    conflicts[g2].add(g1)
    
    base_specialties = {get_base_specialty(g) for g in specialty_groups}
    for spec in base_specialties:
        same_spec_groups = [g for g in specialty_groups if get_base_specialty(g) == spec]
        if len(same_spec_groups) > 1:
            for g1, g2 in itertools.combinations(same_spec_groups, 2):
                conflicts[g1].add(g2)
                conflicts[g2].add(g1)
    return conflicts

def _can_place_group(group, alignment_num, assignments, conflicts):
    for assigned_group, assigned_alignment in assignments.items():
        if assigned_alignment == alignment_num and assigned_group in conflicts.get(group, set()):
            return False
    return True

def _solve_coloring(groups, conflicts, k, assignments, group_index):
    if group_index == len(groups):
        return assignments
    current_group = groups[group_index]
    for alignment_num in range(k):
        if _can_place_group(current_group, alignment_num, assignments, conflicts):
            assignments[current_group] = alignment_num
            result = _solve_coloring(groups, conflicts, k, assignments, group_index + 1)
            if result: return result
            del assignments[current_group]
    return None

def step3_find_alignments(specialty_groups, conflicts):
    sorted_groups = sorted(specialty_groups, key=lambda g: len(conflicts[g]), reverse=True)
    for k in [2, 3, 4, 5]: # Essaie jusqu'à 5 alignements
        assignments = _solve_coloring(sorted_groups, conflicts, k, {}, 0)
        if assignments:
            final_alignments = [[] for _ in range(k)]
            for group, alignment_num in assignments.items():
                final_alignments[alignment_num].append(group)
            for alignment in final_alignments: alignment.sort()
            return final_alignments
    return None

def step4_assign_students(student_choices, final_alignments, specialty_groups, max_capacity):
    if not final_alignments: return None, []
    group_to_alignment_map = {group: i for i, alignment in enumerate(final_alignments) for group in alignment}
    group_rosters = {group: [] for group in specialty_groups}
    unplaced_students = []
    
    sorted_students = sorted(student_choices.keys())
    for student in sorted_students:
        choices = student_choices[student]
        possible_groups_per_spec = [[g for g in specialty_groups if get_base_specialty(g) == spec] for spec in choices]
        best_combination = None
        for group_combination in itertools.product(*possible_groups_per_spec):
            g1, g2, g3 = group_combination
            if len(group_rosters[g1]) < max_capacity and len(group_rosters[g2]) < max_capacity and len(group_rosters[g3]) < max_capacity:
                if len({group_to_alignment_map.get(g) for g in group_combination}) == 3:
                    best_combination = group_combination
                    break
        if best_combination:
            for group in best_combination:
                group_rosters[group].append(student)
        else:
            unplaced_students.append((student, choices))
    return group_rosters, unplaced_students

# --- Interface Streamlit ---

st.set_page_config(layout="wide", page_title="Optimiseur d'Emploi du Temps")

st.title("🚀 Optimiseur d'Emploi du Temps des Spécialités")
st.write("Cet outil génère un emploi du temps optimisé pour minimiser le nombre de créneaux (alignements) tout en respectant les 3 vœux de chaque élève.")

# --- Colonne de gauche pour les paramètres ---
with st.sidebar:
    st.header("⚙️ Paramètres")
    
    # Widget pour charger le fichier
    uploaded_file = st.file_uploader(
        "1. Chargez le fichier CSV des élèves",
        type=['csv']
    )
    
    # Widget pour la capacité max
    max_capacity = st.number_input(
        "2. Capacité maximale par groupe de spécialité",
        min_value=1, value=25, step=1
    )

    # Bouton pour lancer l'analyse
    run_button = st.button("Lancer l'Optimisation", type="primary")

# --- Zone principale pour les résultats ---
if run_button:
    if uploaded_file is not None:
        # Lire et décoder le fichier
        file_content = uploaded_file.getvalue().decode("utf-8")
        
        with st.spinner("Analyse en cours... L'algorithme explore les possibilités..."):
            # Exécution de l'algorithme complet
            student_choices = parse_student_data(file_content)
            
            st.info(f"{len(student_choices)} élèves chargés avec succès.")

            # Étape 1
            groups, counts, logs = step1_preprocess_and_create_groups(student_choices, max_capacity)
            df_counts = pd.DataFrame.from_dict(counts, orient='index', columns=['Effectif']).sort_values('Effectif', ascending=False)
            st.subheader("📊 Étape 1 : Effectifs et Groupes")
            st.dataframe(df_counts)
            for log in logs:
                st.info(log)

            # Étape 2
            conflicts = step2_build_conflict_graph(groups, student_choices)
            st.subheader("🔗 Étape 2 : Conflits entre Spécialités")
            st.write(f"{len(conflicts)} groupes ont des conflits. Un conflit signifie que deux spécialités ne peuvent pas avoir lieu en même temps.")

            # Étape 3
            final_alignments = step3_find_alignments(groups, conflicts)
            st.subheader("🗓️ Étape 3 : Création des Alignements")

            # Étape 4 & Affichage des résultats
            if final_alignments:
                st.success(f"✅ Solution optimale trouvée avec **{len(final_alignments)} alignements** !")
                
                group_rosters, unplaced_students = step4_assign_students(student_choices, final_alignments, groups, max_capacity)
                
                st.subheader("📝 Analyse des Résultats")
                
                col1, col2 = st.columns(2)
                col1.metric("Nombre d'alignements", len(final_alignments))
                col2.metric("Élèves non placés", len(unplaced_students), delta_color="inverse")

                if unplaced_students:
                    st.warning("Certains élèves n'ont pas pu être placés avec leurs 3 vœux :")
                    for student, choices in unplaced_students:
                        st.write(f"- {student} ({', '.join(choices)})")

                st.subheader("📋 Composition des Alignements et Répartition")
                for i, alignment in enumerate(final_alignments):
                    with st.expander(f"**Alignement {i+1}** : {', '.join(alignment)}", expanded=True):
                        for group_name in sorted(alignment):
                            roster = group_rosters.get(group_name, [])
                            st.markdown(f"**{group_name}** ({len(roster)} élèves)")
                            # Affichage en colonnes pour la lisibilité
                            if roster:
                                num_cols = 4
                                cols = st.columns(num_cols)
                                for idx, student in enumerate(sorted(roster)):
                                    cols[idx % num_cols].write(f"- {student}")

            else:
                st.error("❌ Aucune solution trouvée avec 5 alignements ou moins. Les contraintes sont trop fortes.")
                
    else:
        st.warning("Veuillez charger un fichier CSV pour commencer.")
else:
    st.info("Configurez les paramètres dans la barre latérale et cliquez sur 'Lancer l'Optimisation'.")
