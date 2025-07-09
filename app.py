# app.py
import streamlit as st
import pandas as pd
import random
from io import StringIO
import csv
from math import ceil
from collections import defaultdict, Counter
import itertools

# --- CONFIGURATION DE LA PAGE ---
st.set_page_config(layout="wide", page_title="Tableau de Bord de l'Optimiseur")

# --- FONCTIONS DE BASE ET DE L'ALGORITHME (Robustes et Complètes) ---

def get_base_specialty(group_name):
    return group_name.split(' G')[0]

def parse_student_data(file_content):
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

def step1_create_groups_from_counts(specialty_counts, max_capacity):
    """Crée les groupes dédoublés à partir des effectifs."""
    specialty_groups = []
    for spec, count in sorted(specialty_counts.items()):
        num_groups = ceil(count / max_capacity) if count > 0 else 0
        for i in range(1, num_groups + 1):
            specialty_groups.append(f"{spec} G{i}")
    return specialty_groups

def filter_choices_for_cned(student_choices, specs_to_externalize):
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

def step2_build_conflict_graph(specialty_groups, student_choices):
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

def generate_candidate_solution(groups, conflicts, max_alignments):
    assignments = {}
    sorted_groups = sorted(groups, key=lambda g: len(conflicts.get(g, set())), reverse=True)
    
    for group in sorted_groups:
        possible_alignments = list(range(max_alignments))
        random.shuffle(possible_alignments)
        placed = False
        for align_idx in possible_alignments:
            is_valid = all(group not in conflicts.get(pg, set()) for pg, pa in assignments.items() if pa == align_idx)
            if is_valid:
                assignments[group] = align_idx
                placed = True
                break
        if not placed: return None
            
    final_alignments = [[] for _ in range(max_alignments)]
    for group, alignment_num in assignments.items():
        final_alignments[alignment_num].append(group)
    for alignment in final_alignments: alignment.sort()
    
    return final_alignments

def evaluate_solution_performance(student_choices, alignments, max_capacity):
    if not alignments: return None
    group_to_alignment_map = {g: i for i, al in enumerate(alignments) for g in al}
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
                        best_placement = group_combination; break
                if best_placement: break
            if best_placement: break
        
        if best_placement:
            for group in best_placement: rosters[group].append(student)
            placements[len(best_placement)] += 1
            placed_specs = {get_base_specialty(g) for g in best_placement}
            for original_choice in choices:
                if original_choice not in placed_specs:
                    dropped_courses.append({'Élève': student, 'Option non placée': original_choice, 'Raison': 'Conflit d\'emploi du temps'})
        else:
            placements[0] += 1
            for choice in choices: dropped_courses.append({'Élève': student, 'Option non placée': choice, 'Raison': 'Conflit majeur'})

    total_students_to_place = sum(1 for choices in student_choices.values() if choices)
    if total_students_to_place == 0: total_students_to_place = 1
    score = placements[3] * 1000 + placements[2] * 100 + placements[1] * 1
    kpis = {
        'score': score, 'placements': placements,
        'percent_3_specs': (placements[3] / total_students_to_place * 100),
        'percent_2_specs': (placements[2] / total_students_to_place * 100),
        'percent_1_spec': (placements[1] / total_students_to_place * 100),
    }
    return {'alignments': alignments, 'rosters': rosters, 'kpis': kpis, 'dropped_courses': dropped_courses}

# --- NOUVELLE FONCTION D'AFFICHAGE CLAIRE ---
def display_solution(solution, index):
    kpis, alignments, rosters, dropped = solution['kpis'], solution['alignments'], solution['rosters'], solution['dropped_courses']

    with st.container(border=True):
        st.subheader(f"Proposition de Combinaison #{index}")
        st.write("**Indicateurs de Performance**")
        c1, c2, c3 = st.columns(3)
        c1.metric("Élèves avec 3 options servies", f"{kpis['placements'][3]} ({kpis['percent_3_specs']:.1f}%)")
        c2.metric("Élèves avec 2 options servies", f"{kpis['placements'][2]} ({kpis['percent_2_specs']:.1f}%)")
        c3.metric("Élèves avec 1 ou 0 option", f"{kpis['placements'][1] + kpis['placements'][0]}")

        if dropped:
            with st.expander("Voir le détail des options non placées (conflit ou CNED)"):
                st.dataframe(pd.DataFrame(dropped).sort_values(by='Raison'), use_container_width=True)

        st.markdown("---")
        st.write("**Visualisation des Alignements**")
        for i, alignment in enumerate(alignments):
            if not alignment: continue
            with st.container(border=True):
                st.markdown(f"#### Alignement {i+1}")
                # Grille de 3 colonnes pour une bonne lisibilité
                cols = st.columns(3)
                for j, group_name in enumerate(sorted(alignment)):
                    with cols[j % 3]:
                        st.markdown(f"##### {group_name}")
                        st.markdown(f"*{len(rosters.get(group_name, []))} élèves*")
                        with st.expander("Voir la liste"):
                            for student in sorted(rosters.get(group_name, [])):
                                st.write(f"- {student}")

# --- INTERFACE STREAMLIT PRINCIPALE ---
st.title("Tableau de Bord : Optimiseur d'Emploi du Temps")

if 'solutions' not in st.session_state: st.session_state.solutions = []

with st.sidebar:
    st.header("1. Paramètres")
    uploaded_file = st.file_uploader("Chargez le fichier CSV des élèves", type=['csv'])
    max_capacity = st.number_input("Capacité max par groupe", min_value=1, value=25, step=1)
    st.header("2. Stratégie d'Optimisation")
    max_alignments = st.slider("Nombre maximal d'alignements souhaité", 2, 5, 3)
    num_iterations = st.select_slider("Précision de la recherche", options=[10, 50, 100, 200, 500, 1000], value=100)

if uploaded_file:
    file_content = uploaded_file.getvalue().decode("utf-8")
    original_student_choices = parse_student_data(file_content)
    
    st.header("Analyse Initiale des Données")
    with st.expander("Cliquez pour voir le décompte et les groupes créés", expanded=True):
        initial_counts = Counter([spec for choices in original_student_choices.values() for spec in choices])
        df_counts = pd.DataFrame.from_dict(initial_counts, orient='index', columns=['Effectif']).sort_values('Effectif', ascending=False)
        
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Effectifs par spécialité**")
            st.dataframe(df_counts)
        with c2:
            st.markdown(f"**Groupes à planifier (capacité max: {max_capacity})**")
            initial_groups = step1_create_groups_from_counts(initial_counts, max_capacity)
            st.json(initial_groups)

    st.header("Étape 1 : Stratégie d'Externalisation (CNED)")
    # Le slider pour le seuil est de retour
    cned_threshold = st.slider("Définir le seuil d'effectif pour proposer une externalisation", 1, 20, 5)
    candidate_specs = sorted([spec for spec, count in initial_counts.items() if count <= cned_threshold])
    specs_to_externalize = st.multiselect(
        "Vérifiez/modifiez les spécialités à externaliser :",
        options=sorted(initial_counts.keys()), default=candidate_specs
    )

    st.header("Étape 2 : Génération de Solutions")
    col_btn1, col_btn2 = st.columns([3, 1])
    if col_btn1.button("Trouver la MEILLEURE Combinaison", type="primary", use_container_width=True):
        with st.spinner(f"Recherche de la meilleure solution sur {num_iterations} tentatives..."):
            filtered_choices, cned_assign = filter_choices_for_cned(original_student_choices, specs_to_externalize)
            
            # Recalculer les effectifs et les groupes à planifier après filtrage
            planning_counts = Counter([spec for choices in filtered_choices.values() for spec in choices])
            groups_to_plan = step1_create_groups_from_counts(planning_counts, max_capacity)
            conflicts = step2_build_conflict_graph(groups_to_plan, filtered_choices)

            best_solution = None
            for i in range(num_iterations):
                candidate_alignments = generate_candidate_solution(groups_to_plan, conflicts, max_alignments)
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
    if col_btn2.button("Réinitialiser", use_container_width=True):
        st.session_state.solutions = []
        st.rerun()

    if st.session_state.solutions:
        st.header("Étape 3 : Historique des Propositions")
        st.info("Chaque proposition est stable. Vous pouvez relancer la recherche pour trouver d'autres alternatives.")
        for i, solution in reversed(list(enumerate(st.session_state.solutions))):
            display_solution(solution, i + 1)
else:
    st.info("Veuillez commencer par charger un fichier CSV dans le panneau de gauche.")
