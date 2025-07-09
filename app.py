# app.py
import streamlit as st
import pandas as pd
import csv
from io import StringIO
from math import ceil
from collections import defaultdict, Counter
import itertools

# --- Fonctions de l'algorithme (légèrement modifiées pour la flexibilité) ---

def get_base_specialty(group_name):
    return group_name.split(' G')[0]

def parse_student_data(file_content):
    student_choices = {}
    f = StringIO(file_content)
    try:
        sniffer = csv.Sniffer()
        dialect = sniffer.sniff(f.read(1024), delimiters=',;')
        f.seek(0)
        reader = csv.reader(f, dialect)
    except csv.Error:
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

# NOUVEAU: Fonction pour filtrer les choix des élèves
def filter_choices_for_cned(student_choices, specs_to_externalize):
    filtered_choices = {}
    cned_assignments = []
    
    for student, choices in student_choices.items():
        student_cned_specs = []
        student_retained_specs = []

        for spec in choices:
            if spec in specs_to_externalize:
                student_cned_specs.append(spec)
            else:
                student_retained_specs.append(spec)
        
        filtered_choices[student] = student_retained_specs
        
        if student_cned_specs:
            for cned_spec in student_cned_specs:
                cned_assignments.append({'Élève': student, 'Spécialité via CNED': cned_spec})

    return filtered_choices, cned_assignments

# Les fonctions step1, step2, step3, ... restent majoritairement les mêmes
# Elles fonctionneront sur les données "filtrées"
# ... (code des étapes de l'algorithme, voir le bloc complet plus bas)
def step1_preprocess_and_create_groups(student_choices, max_capacity):
    # Les choix peuvent maintenant contenir 2 ou 3 spé
    all_chosen_specialties = [spec for choices in student_choices.values() for spec in choices if choices]
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
    # Gère les élèves avec 2 ou 3 choix
    for student, choices in student_choices.items():
        if len(choices) >= 2:
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
    if group_index == len(groups): return assignments
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
    # Tente de trouver la solution avec le moins d'alignements possible
    for k in range(2, 6): # On teste 2, 3, 4, 5 alignements
        assignments = _solve_coloring(sorted_groups, conflicts, k, {}, 0)
        if assignments:
            final_alignments = [[] for _ in range(k)]
            for group, alignment_num in assignments.items():
                final_alignments[alignment_num].append(group)
            for alignment in final_alignments: alignment.sort()
            return final_alignments
    return None

# MODIFIÉ: Gère les élèves avec 2 ou 3 spécialités à placer
def step4_assign_students(student_choices, final_alignments, specialty_groups, max_capacity):
    if not final_alignments: return None, []
    group_to_alignment_map = {group: i for i, alignment in enumerate(final_alignments) for group in alignment}
    group_rosters = {group: [] for group in specialty_groups}
    unplaced_students = []
    
    sorted_students = sorted(student_choices.keys())

    for student in sorted_students:
        choices = student_choices[student]
        if not choices: continue # Cet élève n'a plus de cours à planifier

        num_choices_to_place = len(choices)
        
        possible_groups_per_spec = [[g for g in specialty_groups if get_base_specialty(g) == spec] for spec in choices]
        
        best_combination = None
        for group_combination in itertools.product(*possible_groups_per_spec):
            # Vérifier capacité
            if any(len(group_rosters[g]) >= max_capacity for g in group_combination):
                continue
            
            # Vérifier que les alignements sont uniques
            if len({group_to_alignment_map.get(g) for g in group_combination}) == num_choices_to_place:
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

st.title("🚀 Outil d'Aide à la Décision pour Emploi du Temps")
st.info("Cette application vous aide à trouver le meilleur compromis en proposant d'externaliser les spécialités à faible effectif.")

# --- Colonne de gauche pour les paramètres ---
with st.sidebar:
    st.header("⚙️ Paramètres de Simulation")
    
    uploaded_file = st.file_uploader(
        "1. Chargez le fichier CSV des élèves", type=['csv']
    )
    
    max_capacity = st.number_input(
        "2. Capacité max par groupe de spécialité",
        min_value=1, value=25, step=1
    )

# --- Zone principale ---
if uploaded_file is not None:
    file_content = uploaded_file.getvalue().decode("utf-8")
    original_student_choices = parse_student_data(file_content)
    
    # Calcul initial des effectifs pour l'aide à la décision
    initial_counts = Counter([spec for choices in original_student_choices.values() for spec in choices])
    df_counts = pd.DataFrame.from_dict(initial_counts, orient='index', columns=['Effectif']).sort_values('Effectif', ascending=True)

    with st.expander("📊 Analyse des Effectifs par Spécialité", expanded=True):
        st.dataframe(df_counts)

    st.header("💡 Phase 1 : Stratégie d'Externalisation (CNED)")
    
    # Widget pour le seuil
    cned_threshold = st.slider(
        "Définir le seuil d'effectif pour proposer une externalisation",
        min_value=1, max_value=20, value=5,
        help="Toutes les spécialités avec un effectif inférieur ou égal à ce seuil seront proposées pour le CNED."
    )

    # Identifier les spécialités candidates
    candidate_specs = [spec for spec, count in initial_counts.items() if count <= cned_threshold]
    
    if not candidate_specs:
        st.info("Aucune spécialité ne correspond à ce seuil. Toutes les spécialités seront incluses dans le planning.")
        specs_to_externalize = []
    else:
        st.write("Cochez les spécialités à externaliser. Les élèves concernés n'auront que leurs 2 autres spécialités planifiées.")
        # Utiliser un multiselect pour un affichage propre
        specs_to_externalize = st.multiselect(
            "Spécialités candidates pour une prise en charge par le CNED :",
            options=candidate_specs,
            default=candidate_specs # Toutes sont sélectionnées par défaut
        )
    
    st.divider()
    
    st.header("🚀 Phase 2 : Lancer l'Optimisation")
    if st.button("Trouver le meilleur emploi du temps", type="primary"):
        with st.spinner("Analyse des conflits et recherche de la solution optimale..."):
            
            # 1. Filtrer les choix des élèves selon la stratégie CNED
            filtered_student_choices, cned_assignments = filter_choices_for_cned(
                original_student_choices, specs_to_externalize
            )
            
            # 2. Lancer l'algorithme sur les données filtrées
            groups, counts, logs = step1_preprocess_and_create_groups(filtered_student_choices, max_capacity)
            conflicts = step2_build_conflict_graph(groups, filtered_student_choices)
            final_alignments = step3_find_alignments(groups, conflicts)

            st.header("📈 Phase 3 : Résultats de l'Optimisation")
            if final_alignments:
                group_rosters, unplaced = step4_assign_students(filtered_student_choices, final_alignments, groups, max_capacity)
                
                # Affichage des KPIs
                st.success(f"✅ Solution optimale trouvée avec **{len(final_alignments)} alignements** !")
                col1, col2, col3 = st.columns(3)
                col1.metric("Nombre d'alignements", len(final_alignments))
                col2.metric("Élèves au CNED", len(cned_assignments))
                col3.metric("Élèves non placés", len(unplaced), delta_color="inverse")

                # Affichage des élèves au CNED
                if cned_assignments:
                    st.subheader("👨‍💻 Élèves avec une spécialité externalisée via CNED")
                    df_cned = pd.DataFrame(cned_assignments)
                    st.dataframe(df_cned)

                # Affichage des alignements et des groupes
                st.subheader("📋 Composition des Alignements et Répartition")
                for i, alignment in enumerate(final_alignments):
                    with st.expander(f"**Alignement {i+1}** ({len(alignment)} groupes)", expanded=(len(final_alignments)<=3)):
                        for group_name in sorted(alignment):
                            roster = group_rosters.get(group_name, [])
                            st.markdown(f"**{group_name}** ({len(roster)} élèves)")
                            if roster:
                                num_cols = 4
                                cols = st.columns(num_cols)
                                for idx, student in enumerate(sorted(roster)):
                                    cols[idx % num_cols].write(f"- {student}")
                
                if unplaced:
                    st.warning("Certains élèves n'ont pas pu être placés :")
                    st.write(unplaced)
            else:
                st.error("❌ Aucune solution trouvée. Essayez d'externaliser plus de spécialités ou d'augmenter la capacité des groupes.")

else:
    st.info("Veuillez charger un fichier CSV pour commencer.")
