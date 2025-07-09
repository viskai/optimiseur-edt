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
st.set_page_config(layout="wide", page_title="Moteur d'Optimisation Stratégique")

# --- FONCTIONS DE L'ALGORITHME (AVEC LOGIQUE D'ANCRAGE) ---

def get_base_specialty(group_name):
    return group_name.split(' G')[0]

def parse_student_data(file_content):
    student_choices = {}
    f = StringIO(file_content); reader = csv.reader(f)
    next(reader) # Skip header
    for row in reader:
        if not row: continue
        student_name = row[0].strip()
        specialties = sorted([spec.strip() for spec in row[1:] if spec.strip()])
        if len(specialties) == 3: student_choices[student_name] = specialties
    return student_choices

def step1_create_groups_from_counts(specialty_counts, max_capacity):
    specialty_groups = []
    for spec, count in sorted(specialty_counts.items()):
        num_groups = ceil(count / max_capacity) if count > 0 else 0
        for i in range(1, num_groups + 1):
            specialty_groups.append(f"{spec} G{i}")
    return specialty_groups

def find_anchor_triplet(student_choices):
    """Identifie le triplet de spécialités le plus mutuellement conflictuel."""
    pair_counts = Counter(p for choices in student_choices.values() for p in itertools.combinations(sorted(choices), 2))
    if not pair_counts: return None

    unique_specs = sorted(list(set(c for choices in student_choices.values() for c in choices)))
    best_triplet = None
    max_score = -1

    for triplet in itertools.combinations(unique_specs, 3):
        t = tuple(sorted(triplet))
        p1, p2, p3 = (t[0], t[1]), (t[0], t[2]), (t[1], t[2])
        if pair_counts[p1] > 0 and pair_counts[p2] > 0 and pair_counts[p3] > 0:
            score = pair_counts[p1] + pair_counts[p2] + pair_counts[p3]
            if score > max_score:
                max_score = score
                best_triplet = t
    return best_triplet

def build_conflict_graph(specialty_groups, student_choices):
    conflicts = defaultdict(set)
    for student, choices in student_choices.items():
        if len(choices) >= 2:
            for spec1, spec2 in itertools.combinations(choices, 2):
                groups1 = [g for g in specialty_groups if get_base_specialty(g) == spec1]
                groups2 = [g for g in specialty_groups if get_base_specialty(g) == spec2]
                for g1 in groups1:
                    for g2 in groups2:
                        conflicts[g1].add(g2); conflicts[g2].add(g1)
    
    base_specs = {get_base_specialty(g) for g in specialty_groups}
    for spec in base_specs:
        same_spec_groups = [g for g in specialty_groups if get_base_specialty(g) == spec]
        if len(same_spec_groups) > 1:
            for g1, g2 in itertools.combinations(same_spec_groups, 2):
                conflicts[g1].add(g2); conflicts[g2].add(g1)
    return conflicts

def generate_candidate_solution(groups, conflicts, max_alignments, anchor_triplet=None):
    assignments = {}
    remaining_groups = list(groups)
    
    # Étape d'ancrage : placer le noyau dur en premier
    if anchor_triplet and max_alignments >= 3:
        for i, anchor_spec in enumerate(anchor_triplet):
            # Placer tous les groupes de cette spé (ex: Maths G1, Maths G2)
            anchor_groups = [g for g in remaining_groups if get_base_specialty(g) == anchor_spec]
            for g in anchor_groups:
                assignments[g] = i
            remaining_groups = [g for g in remaining_groups if get_base_specialty(g) != anchor_spec]

    # Placer le reste de manière heuristique
    sorted_groups = sorted(remaining_groups, key=lambda g: len(conflicts.get(g, set())), reverse=True)
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
        if not placed: return None # Impossible de placer ce groupe

    # Formatage final
    final_alignments = [[] for _ in range(max_alignments)]
    for group, alignment_num in assignments.items():
        final_alignments[alignment_num].append(group)
    for alignment in final_alignments: alignment.sort()
    return final_alignments

def evaluate_solution_performance(student_choices, alignments, max_capacity):
    # Logique de cette fonction reste la même, elle est déjà conçue pour le "best effort"
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
    kpis = {'score': score, 'placements': placements,
            'percent_3_specs': (placements[3] / total_students_to_place * 100),
            'percent_2_specs': (placements[2] / total_students_to_place * 100)}
    return {'alignments': alignments, 'rosters': rosters, 'kpis': kpis, 'dropped_courses': dropped_courses}

# --- INTERFACE ET AFFICHAGE ---
def display_solution(solution, index, isolated_spec_groups):
    kpis, alignments, rosters, dropped = solution['kpis'], solution['alignments'], solution['rosters'], solution['dropped_courses']
    
    with st.container(border=True):
        st.subheader(f"Proposition de Combinaison #{index}")
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Élèves avec 3 options servies (ou 2 + 1 isolée/CNED)", f"{kpis['placements'].get(3,0) + kpis['placements'].get(2,0)} ({kpis['percent_3_specs'] + kpis['percent_2_specs']:.1f}%)")
        c2.metric("Élèves avec 2 options servies (sur 3)", f"{kpis['placements'].get(2,0)}")
        c3.metric("Élèves avec 1 ou 0 option", f"{kpis['placements'].get(1,0) + kpis['placements'].get(0,0)}")

        if dropped:
            with st.expander("Voir le détail des options non placées"):
                st.dataframe(pd.DataFrame(dropped).sort_values(by='Raison'), use_container_width=True)

        st.markdown("---")
        # Afficher le cours autonome s'il existe
        if isolated_spec_groups:
            with st.container(border=True):
                st.markdown(f"#### 🔒 Créneau Autonome (Non-aligné)")
                # AFFICHER LES ELEVES DU COURS AUTONOME ICI
                st.markdown(f"##### {isolated_spec_groups[0].split(' G')[0]}")
                st.write("*Ce cours se déroule sur son propre créneau.*")
        
        st.write("**Visualisation des Alignements**")
        for i, alignment in enumerate(alignments):
            if not alignment: continue
            with st.container(border=True):
                st.markdown(f"#### Alignement {i+1}")
                cols = st.columns(3)
                for j, group_name in enumerate(sorted(alignment)):
                    with cols[j % 3]:
                        st.markdown(f"##### {group_name}")
                        st.markdown(f"*{len(rosters.get(group_name, []))} élèves*")
                        with st.expander("Voir la liste"):
                            for student in sorted(rosters.get(group_name, [])):
                                st.write(f"- {student}")

# --- INTERFACE STREAMLIT PRINCIPALE ---
st.title("Moteur d'Optimisation Stratégique pour Emploi du Temps")
if 'solutions' not in st.session_state: st.session_state.solutions = []

with st.sidebar:
    st.header("1. Données & Contraintes")
    uploaded_file = st.file_uploader("Chargez le fichier CSV", type=['csv'])
    max_capacity = st.number_input("Capacité max par groupe", 25)
    
    st.header("2. Stratégies d'Optimisation")
    max_alignments = st.slider("Nombre total de créneaux souhaités", 2, 5, 3)
    isolated_spec = st.selectbox("Isoler un cours 'lourd' sur un créneau autonome ?", [None] + sorted(list(set(c for choices in parse_student_data(uploaded_file.getvalue().decode("utf-8")).values() for c in choices))) if uploaded_file else [None], help="Ce cours sera retiré du puzzle, simplifiant les conflits.")
    
    st.header("3. Précision")
    num_iterations = st.select_slider("Précision de la recherche", [10, 50, 100, 200, 500, 1000], 100)

if uploaded_file:
    file_content = uploaded_file.getvalue().decode("utf-8")
    original_student_choices = parse_student_data(file_content)
    all_specs = sorted(list(set(c for choices in original_student_choices.values() for c in choices)))
    
    st.header("Analyse & Stratégie d'Externalisation (CNED)")
    initial_counts = Counter([spec for choices in original_student_choices.values() for spec in choices])
    cned_threshold = st.slider("Seuil d'effectif pour proposer l'externalisation", 1, 20, 5)
    candidate_specs = sorted([spec for spec, count in initial_counts.items() if count <= cned_threshold])
    specs_to_externalize = st.multiselect("Vérifiez les spécialités à externaliser (CNED) :", all_specs, default=candidate_specs)

    st.header("Lancement de l'Optimisation")
    col_btn1, col_btn2 = st.columns([3, 1])
    if col_btn1.button("Trouver la MEILLEURE Combinaison", type="primary", use_container_width=True):
        with st.spinner(f"Analyse des conflits et recherche de la meilleure solution..."):
            
            # 1. Gérer le cours isolé s'il y en a un
            num_alignments_for_puzzle = max_alignments - 1 if isolated_spec else max_alignments
            if num_alignments_for_puzzle < 1:
                st.error("Erreur : Pas assez d'alignements pour le puzzle après isolation. Augmentez le nombre total de créneaux.")
                st.stop()
            
            choices_for_planning = {}
            isolated_assignments = defaultdict(list)
            cned_assignments = defaultdict(list)

            for student, choices in original_student_choices.items():
                retained = []
                for spec in choices:
                    if spec in specs_to_externalize: cned_assignments[student].append(spec)
                    elif spec == isolated_spec: isolated_assignments[student].append(spec)
                    else: retained.append(spec)
                choices_for_planning[student] = retained

            # 2. Identifier le noyau dur du problème RESTANT
            anchor = find_anchor_triplet(choices_for_planning)
            if anchor:
                st.info(f"**Ancrage automatique identifié :** Le trio `{anchor[0]}`, `{anchor[1]}` et `{anchor[2]}` est le plus conflictuel. Il servira de base à la construction.")

            # 3. Créer les groupes et le graphe de conflits pour le puzzle
            planning_counts = Counter(s for c in choices_for_planning.values() for s in c)
            groups_to_plan = step1_create_groups_from_counts(planning_counts, max_capacity)
            conflicts = build_conflict_graph(groups_to_plan, choices_for_planning)

            # 4. Lancer la recherche
            best_solution = None
            for _ in range(num_iterations):
                candidate = generate_candidate_solution(groups_to_plan, conflicts, num_alignments_for_puzzle, anchor)
                if candidate:
                    result = evaluate_solution_performance(choices_for_planning, candidate, max_capacity)
                    if not best_solution or result['kpis']['score'] > best_solution['kpis']['score']: best_solution = result
            
            # 5. Formater et stocker les résultats
            if best_solution:
                # Ajouter les élèves sacrifiés (CNED, Isolé) à la liste pour l'affichage
                for student, specs in cned_assignments.items():
                    for spec in specs: best_solution['dropped_courses'].append({'Élève': student, 'Option non placée': spec, 'Raison': 'Externalisé (CNED)'})
                for student, specs in isolated_assignments.items():
                    for spec in specs: best_solution['dropped_courses'].append({'Élève': student, 'Option non placée': spec, 'Raison': 'Cours Autonome'})
                
                # Stocker le nom du groupe isolé pour l'affichage
                isolated_groups = step1_create_groups_from_counts({isolated_spec: len(isolated_assignments)}, max_capacity) if isolated_spec else []
                best_solution['isolated_groups'] = isolated_groups

                st.session_state.solutions.append(best_solution)
                st.success("Proposition optimale trouvée et ajoutée à l'historique !")
            else:
                st.error("Aucune solution trouvée. Les contraintes sont trop fortes. Essayez d'augmenter les créneaux, d'isoler un cours ou d'externaliser plus d'options.")
    
    if col_btn2.button("Réinitialiser", use_container_width=True):
        st.session_state.solutions = []
        st.rerun()

    if st.session_state.solutions:
        st.header("Historique des Propositions")
        for i, solution in reversed(list(enumerate(st.session_state.solutions))):
            display_solution(solution, i + 1, solution.get('isolated_groups', []))
else:
    st.info("Chargez un fichier pour commencer.")
