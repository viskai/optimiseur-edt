# app.py
import streamlit as st
import pandas as pd
import random
import copy
from io import StringIO
import csv
from math import ceil
from collections import defaultdict, Counter
import itertools

# --- CONFIGURATION DE LA PAGE ---
st.set_page_config(layout="wide", page_title="Optimiseur d'Emploi du Temps")

# --- FONCTIONS DE BASE ET DE L'ALGORITHME ---

def get_base_specialty(group_name):
    """Extrait le nom de la spécialité de base d'un nom de groupe."""
    return group_name.split(' G')[0]

def parse_student_data(file_content):
    """Lit les données des élèves et retourne un dictionnaire de leurs choix."""
    student_choices = {}
    f = StringIO(file_content)
    try:
        dialect = csv.Sniffer().sniff(f.read(1024), delimiters=',;')
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

def filter_choices_for_cned(student_choices, specs_to_externalize):
    """Filtre les choix des élèves en fonction des spécialités externalisées."""
    filtered_choices = {}
    cned_assignments = defaultdict(list)
    for student, choices in student_choices.items():
        retained_specs = []
        for spec in choices:
            if spec in specs_to_externalize:
                cned_assignments[student].append(spec)
            else:
                retained_specs.append(spec)
        filtered_choices[student] = retained_specs
    return filtered_choices, cned_assignments

# --- FONCTIONS MANQUANTES RÉINTÉGRÉES ---
def step1_preprocess_and_create_groups(student_choices, max_capacity):
    """Étape 1: Compte les effectifs et crée les groupes de spécialités."""
    all_chosen_specialties = [spec for choices in student_choices.values() for spec in choices if choices]
    specialty_counts = Counter(all_chosen_specialties)
    specialty_groups = []
    
    for spec, count in sorted(specialty_counts.items()):
        num_groups = ceil(count / max_capacity)
        for i in range(1, num_groups + 1):
            specialty_groups.append(f"{spec} G{i}")
            
    return specialty_groups, specialty_counts, [] # Le 3ème return est pour la compatibilité

def step2_build_conflict_graph(specialty_groups, student_choices):
    """Étape 2: Construit un graphe de conflits entre les groupes."""
    conflicts = defaultdict(set)
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

# --- NOUVELLE LOGIQUE D'OPTIMISATION "BEST EFFORT" ---
def generate_candidate_solution(groups, conflicts, max_alignments):
    """Tente de générer une affectation de groupes à des alignements de manière aléatoire et heuristique."""
    assignments = {}
    sorted_groups = sorted(groups, key=lambda g: len(conflicts.get(g, set())), reverse=True)
    
    for group in sorted_groups:
        possible_alignments = list(range(max_alignments))
        random.shuffle(possible_alignments)
        placed = False
        for align_idx in possible_alignments:
            is_valid = True
            for placed_group, placed_align in assignments.items():
                if placed_align == align_idx and group in conflicts.get(placed_group, set()):
                    is_valid = False
                    break
            if is_valid:
                assignments[group] = align_idx
                placed = True
                break
        if not placed:
            return None
            
    final_alignments = [[] for _ in range(max_alignments)]
    for group, alignment_num in assignments.items():
        final_alignments[alignment_num].append(group)
    for alignment in final_alignments: alignment.sort()
    
    return final_alignments

def evaluate_solution_performance(student_choices, alignments, max_capacity):
    """Pour une configuration d'alignement donnée, répartit les élèves et calcule les KPIs."""
    if not alignments: return None

    group_to_alignment_map = {group: i for i, alignment in enumerate(alignments) for group in alignment}
    all_groups = list(group_to_alignment_map.keys())
    rosters = {group: [] for group in all_groups}
    
    placements = {3: 0, 2: 0, 1: 0, 0: 0}
    dropped_courses = []

    for student, choices in sorted(student_choices.items()):
        if not choices: continue
        best_placement = None
        for num_to_place in range(len(choices), 0, -1):
            for combo_choices in itertools.combinations(choices, num_to_place):
                possible_groups_per_spec = [[g for g in all_groups if get_base_specialty(g) == spec] for spec in combo_choices]
                if not all(possible_groups_per_spec): continue

                for group_combination in itertools.product(*possible_groups_per_spec):
                    if (all(len(rosters[g]) < max_capacity for g in group_combination) and 
                        len({group_to_alignment_map.get(g) for g in group_combination}) == num_to_place):
                        best_placement = group_combination
                        break
                if best_placement: break
            if best_placement: break
        
        if best_placement:
            for group in best_placement:
                rosters[group].append(student)
            placements[len(best_placement)] += 1
            placed_specs = {get_base_specialty(g) for g in best_placement}
            for original_choice in choices:
                if original_choice not in placed_specs:
                    dropped_courses.append({'Élève': student, 'Option non placée': original_choice, 'Raison': 'Conflit d\'emploi du temps'})
        else:
            placements[0] += 1
            for choice in choices:
                dropped_courses.append({'Élève': student, 'Option non placée': choice, 'Raison': 'Conflit d\'emploi du temps'})

    total_students = len(student_choices) if student_choices else 1 # Avoid division by zero
    total_students_to_place = sum(1 for choices in student_choices.values() if choices)
    if total_students_to_place == 0: total_students_to_place = 1

    score = placements[3] * 1000 + placements[2] * 100 + placements[1] * 1
    
    kpis = {
        'score': score,
        'placements': placements,
        'total_students_to_place': total_students_to_place,
        'percent_3_specs': (placements[3] / total_students_to_place * 100),
        'percent_2_specs': (placements[2] / total_students_to_place * 100),
        'percent_1_spec': (placements[1] / total_students_to_place * 100),
    }

    return {'alignments': alignments, 'rosters': rosters, 'kpis': kpis, 'dropped_courses': dropped_courses}

# --- FONCTIONS D'AFFICHAGE ---
def display_solution(solution, index):
    """Affiche une solution complète de manière claire."""
    kpis = solution['kpis']
    alignments = solution['alignments']
    rosters = solution['rosters']
    dropped = solution['dropped_courses']

    with st.container(border=True):
        st.subheader(f"Proposition de Combinaison #{index}")
        
        st.write("**Indicateurs de Performance**")
        c1, c2, c3 = st.columns(3)
        c1.metric("Élèves avec 3 options servies", f"{kpis['placements'][3]} ({kpis['percent_3_specs']:.1f}%)")
        c2.metric("Élèves avec 2 options servies", f"{kpis['placements'][2]} ({kpis['percent_2_specs']:.1f}%)")
        c3.metric("Élèves avec 1 ou 0 option", f"{kpis['placements'][1] + kpis['placements'][0]}")

        if dropped:
            with st.expander("Voir les élèves avec des options incompatibles ou externalisées"):
                st.dataframe(pd.DataFrame(dropped), use_container_width=True)

        for i, alignment in enumerate(alignments):
            if not alignment: continue
            st.markdown(f"--- \n**Alignement {i+1}**")
            cols = st.columns(len(alignment)) if alignment else []
            for j, group_name in enumerate(alignment):
                with cols[j]:
                    st.markdown(f"**{group_name}**")
                    st.markdown(f"*{len(rosters[group_name])} élèves*")
                    for student in sorted(rosters.get(group_name, [])):
                        st.write(f"- {student}")

# --- INTERFACE STREAMLIT PRINCIPALE ---
st.title("🔬 Optimiseur d'Emploi du Temps (Version Avancée)")
st.caption("Un outil d'aide à la décision pour trouver la meilleure organisation possible.")

if 'solutions' not in st.session_state:
    st.session_state.solutions = []

with st.sidebar:
    st.header("1. Chargement des Données")
    uploaded_file = st.file_uploader("Chargez le fichier CSV des élèves", type=['csv'])
    max_capacity = st.number_input("Capacité max par groupe", min_value=1, value=35, step=1)
    st.header("2. Stratégie d'Optimisation")
    max_alignments = st.slider("Nombre maximal d'alignements souhaité", 2, 5, 3)
    num_iterations = st.select_slider(
        "Précision de la recherche", 
        options=[10, 50, 100, 200, 500, 1000], value=100)

if uploaded_file:
    file_content = uploaded_file.getvalue().decode("utf-8")
    original_student_choices = parse_student_data(file_content)
    
    st.header("Étape 1 : Stratégie d'Externalisation (CNED)")
    initial_counts = Counter([spec for choices in original_student_choices.values() for spec in choices])
    candidate_specs = sorted([spec for spec, count in initial_counts.items() if count <= 10])
    specs_to_externalize = st.multiselect(
        "Sélectionnez les spécialités à faible effectif à externaliser (via CNED) :",
        options=sorted(initial_counts.keys()),
        default=candidate_specs
    )

    st.header("Étape 2 : Génération de Solutions")
    col_btn1, col_btn2 = st.columns(2)
    if col_btn1.button("Trouver la MEILLEURE Combinaison", type="primary"):
        with st.spinner(f"Recherche de la meilleure solution sur {num_iterations} tentatives..."):
            filtered_choices, cned_assign = filter_choices_for_cned(original_student_choices, specs_to_externalize)
            all_groups, _, _ = step1_preprocess_and_create_groups(filtered_choices, max_capacity)
            conflicts = step2_build_conflict_graph(all_groups, filtered_choices)

            best_solution = None
            for i in range(num_iterations):
                candidate_alignments = generate_candidate_solution(all_groups, conflicts, max_alignments)
                if candidate_alignments:
                    result = evaluate_solution_performance(filtered_choices, candidate_alignments, max_capacity)
                    if not best_solution or result['kpis']['score'] > best_solution['kpis']['score']:
                        best_solution = result
            
            if best_solution:
                for student, specs in cned_assign.items():
                    for spec in specs:
                        best_solution['dropped_courses'].append({'Élève': student, 'Option non placée': spec, 'Raison': 'Externalisé (CNED)'})
                
                st.session_state.solutions.append(best_solution)
                st.success("Une nouvelle proposition optimale a été trouvée et ajoutée à l'historique ci-dessous !")
            else:
                st.error("Impossible de trouver une solution valide. Essayez d'augmenter le nombre d'alignements ou d'externaliser plus de spécialités.")

    if col_btn2.button("Réinitialiser l'historique"):
        st.session_state.solutions = []
        st.rerun()

    if st.session_state.solutions:
        st.header("Étape 3 : Historique des Propositions")
        st.info("Chaque proposition est stable. Vous pouvez relancer la recherche pour trouver d'autres alternatives.")
        
        for i, solution in reversed(list(enumerate(st.session_state.solutions))):
            display_solution(solution, i + 1)
else:
    st.info("Veuillez commencer par charger un fichier CSV dans le panneau de gauche.")
