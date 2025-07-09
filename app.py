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
st.set_page_config(layout="wide", page_title="Moteur de Diagnostic & d'Optimisation")

# --- FONCTIONS DE L'ALGORITHME (AVEC PARSER ROBUSTE) ---

def get_base_specialty(group_name): return group_name.split(' G')[0]

def parse_student_data(file_content):
    """Parser CSV robuste qui détecte automatiquement le délimiteur (virgule ou point-virgule)."""
    student_choices = {}
    if not file_content.strip(): return student_choices # Gérer fichier vide

    f = StringIO(file_content)
    try:
        dialect = csv.Sniffer().sniff(f.read(1024), delimiters=',;')
        f.seek(0)
        reader = csv.reader(f, dialect)
    except csv.Error:
        f.seek(0)
        reader = csv.reader(f)
        
    try:
        header = next(reader)
        for row in reader:
            if not row or not row[0].strip(): continue
            student_name = row[0].strip()
            specialties = sorted([spec.strip() for spec in row[1:] if spec.strip()])
            if len(specialties) == 3: student_choices[student_name] = specialties
    except (StopIteration, IndexError):
        # Le fichier est probablement mal formaté ou vide
        st.error("Impossible de lire le fichier. Veuillez vérifier qu'il est bien au format CSV et qu'il contient des données.")
        return {}
        
    return student_choices

def step1_create_groups_from_counts(specialty_counts, max_capacity):
    specialty_groups = []
    for spec, count in sorted(specialty_counts.items()):
        num_groups = ceil(count / max_capacity) if count > 0 else 0
        for i in range(1, num_groups + 1): specialty_groups.append(f"{spec} G{i}")
    return specialty_groups

def find_anchor_triplet(student_choices):
    pair_counts = Counter(p for c in student_choices.values() for p in itertools.combinations(sorted(c), 2))
    if not pair_counts: return None
    unique_specs = sorted(list(set(s for c in student_choices.values() for s in c)))
    best_triplet, max_score = None, -1
    for triplet in itertools.combinations(unique_specs, 3):
        t = tuple(sorted(triplet))
        p1, p2, p3 = (t[0], t[1]), (t[0], t[2]), (t[1], t[2])
        if pair_counts[p1] > 0 and pair_counts[p2] > 0 and pair_counts[p3] > 0:
            score = pair_counts[p1] + pair_counts[p2] + pair_counts[p3]
            if score > max_score: max_score, best_triplet = score, t
    return best_triplet

def build_conflict_graph(specialty_groups, student_choices):
    conflicts = defaultdict(set)
    for student, choices in student_choices.items():
        if len(choices) >= 2:
            for spec1, spec2 in itertools.combinations(choices, 2):
                g1s, g2s = [g for g in specialty_groups if get_base_specialty(g) == spec1], [g for g in specialty_groups if get_base_specialty(g) == spec2]
                for g1 in g1s:
                    for g2 in g2s: conflicts[g1].add(g2); conflicts[g2].add(g1)
    base_specs = {get_base_specialty(g) for g in specialty_groups}
    for spec in base_specs:
        same_spec_groups = [g for g in specialty_groups if get_base_specialty(g) == spec]
        if len(same_spec_groups) > 1:
            for g1, g2 in itertools.combinations(same_spec_groups, 2): conflicts[g1].add(g2); conflicts[g2].add(g1)
    return conflicts

def generate_candidate_solution(groups, conflicts, max_alignments, anchor_triplet=None):
    assignments, remaining_groups = {}, list(groups)
    if anchor_triplet and max_alignments >= 3:
        for i, anchor_spec in enumerate(anchor_triplet):
            anchor_groups = [g for g in remaining_groups if get_base_specialty(g) == anchor_spec]
            for g in anchor_groups: assignments[g] = i
            remaining_groups = [g for g in remaining_groups if get_base_specialty(g) != anchor_spec]
    sorted_groups = sorted(remaining_groups, key=lambda g: len(conflicts.get(g, set())), reverse=True)
    for group in sorted_groups:
        possible_alignments = list(range(max_alignments)); random.shuffle(possible_alignments)
        placed = False
        for align_idx in possible_alignments:
            if all(group not in conflicts.get(pg, set()) for pg, pa in assignments.items() if pa == align_idx):
                assignments[group], placed = align_idx, True; break
        if not placed: return None
    final_alignments = [[] for _ in range(max_alignments)]
    for group, alignment_num in assignments.items(): final_alignments[alignment_num].append(group)
    for alignment in final_alignments: alignment.sort()
    return final_alignments

def evaluate_solution_performance(student_choices, alignments, max_capacity):
    if not alignments: return None
    group_to_alignment_map = {g: i for i, al in enumerate(alignments) for g in al}
    all_groups, rosters = list(group_to_alignment_map.keys()), {g: [] for g in list(group_to_alignment_map.keys())}
    placements, dropped_courses = {3: 0, 2: 0, 1: 0, 0: 0}, []
    for student, choices in sorted(student_choices.items()):
        if not choices: continue
        best_placement = None
        for num_to_place in range(len(choices), 0, -1):
            for combo_choices in itertools.combinations(choices, num_to_place):
                possible_groups_per_spec = [[g for g in all_groups if get_base_specialty(g) == spec] for spec in combo_choices]
                if not all(possible_groups_per_spec): continue
                for group_combination in itertools.product(*possible_groups_per_spec):
                    if (all(len(rosters[g]) < max_capacity for g in group_combination) and len({group_to_alignment_map.get(g) for g in group_combination}) == num_to_place):
                        best_placement = group_combination; break
                if best_placement: break
            if best_placement: break
        if best_placement:
            for group in best_placement: rosters[group].append(student)
            placements[len(best_placement)] += 1
            placed_specs = {get_base_specialty(g) for g in best_placement}
            for original_choice in choices:
                if original_choice not in placed_specs: dropped_courses.append({'Élève': student, 'Option non placée': original_choice, 'Raison': 'Conflit d\'emploi du temps'})
        else:
            placements[0] += 1
            for choice in choices: dropped_courses.append({'Élève': student, 'Option non placée': choice, 'Raison': 'Conflit majeur'})
    total_students_to_place = sum(1 for c in student_choices.values() if c)
    if total_students_to_place == 0: total_students_to_place = 1
    score = placements[3] * 1000 + placements[2] * 100 + placements[1] * 1
    kpis = {'score': score, 'placements': placements, 'percent_3_specs': (placements[3] / total_students_to_place * 100), 'percent_2_specs': (placements[2] / total_students_to_place * 100)}
    return {'alignments': alignments, 'rosters': rosters, 'kpis': kpis, 'dropped_courses': dropped_courses}

def create_conflict_graph_dot(student_choices):
    pair_counts = Counter(p for choices in student_choices.values() for p in itertools.combinations(sorted(choices), 2))
    all_specs = sorted(list(set(s for choices in student_choices.values() for s in choices)))
    if not all_specs: return "graph G {}"
    dot_lines = ['graph G {', '  layout="neato";', '  node [shape=circle, style=filled, fillcolor="#A8DADC", fontname="Helvetica"];', '  edge [fontname="Helvetica", fontsize=10];']
    for spec in all_specs: dot_lines.append(f'  "{spec}";')
    max_count = max(pair_counts.values()) if pair_counts else 1
    for (spec1, spec2), count in pair_counts.items():
        penwidth = 1 + (count / max_count) * 6
        color = "#BDBDBD" # Gris clair par défaut
        if penwidth > 5: color = "#E63946" # Rouge
        elif penwidth > 3: color = "#F4A261" # Orange
        dot_lines.append(f'  "{spec1}" -- "{spec2}" [label="{count}", penwidth={penwidth:.2f}, color="{color}"];')
    dot_lines.append('}')
    return "\n".join(dot_lines)

def create_conflict_matrix(student_choices):
    pair_counts = Counter(p for choices in student_choices.values() for p in itertools.combinations(sorted(choices), 2))
    all_specs = sorted(list(set(s for choices in student_choices.values() for s in choices)))
    df = pd.DataFrame(0, index=all_specs, columns=all_specs)
    for (spec1, spec2), count in pair_counts.items(): df.loc[spec1, spec2], df.loc[spec2, spec1] = count, count
    return df.style.background_gradient(cmap='Reds')

def display_solution(solution, index):
    kpis, alignments, rosters, dropped = solution['kpis'], solution['alignments'], solution['rosters'], solution['dropped_courses']
    with st.container(border=True):
        st.subheader(f"Proposition de Combinaison #{index}")
        c1, c2, c3 = st.columns(3)
        c1.metric("Élèves avec 3 vœux respectés", f"{kpis['placements'][3]}")
        c2.metric("Élèves avec 2 vœux sur 3", f"{kpis['placements'][2]}")
        c3.metric("Élèves avec 1 ou 0 vœu", f"{kpis['placements'][1] + kpis['placements'][0]}")
        with st.expander("Voir le bilan détaillé des options non placées"):
            st.dataframe(pd.DataFrame(dropped).sort_values(by='Raison'), use_container_width=True)
        st.markdown("---")
        if solution.get('isolated_groups'):
            with st.container(border=True):
                st.markdown(f"#### 🔒 Créneau Autonome (Non-aligné)")
                isolated_spec_name = solution['isolated_groups'][0].split(' G')[0]
                student_list = [s for s, c in solution['isolated_assign'].items() if isolated_spec_name in c]
                st.markdown(f"##### {isolated_spec_name} ({len(student_list)} élèves)")
                with st.expander("Voir la liste des élèves concernés"): st.write(sorted(student_list))
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
                            for student in sorted(rosters.get(group_name, [])): st.write(f"- {student}")

# --- INTERFACE STREAMLIT PRINCIPALE ---
st.title("Moteur de Diagnostic & d'Optimisation d'Emploi du Temps")
if 'solutions' not in st.session_state: st.session_state.solutions = []

with st.sidebar:
    st.header("1. Données & Contraintes")
    uploaded_file = st.file_uploader("Chargez le fichier CSV", type=['csv'])
    max_capacity = st.number_input("Capacité max par groupe", 25, key="max_cap")
    
    st.header("2. Stratégies d'Optimisation")
    if uploaded_file:
        try:
            # Re-parse to populate selectbox without consuming the uploader object
            file_content_for_sb = uploaded_file.getvalue().decode("utf-8")
            all_specs_from_file = sorted(list(set(c for choices in parse_student_data(file_content_for_sb).values() for c in choices)))
        except:
            all_specs_from_file = []
    else:
        all_specs_from_file = []
    
    max_alignments = st.slider("Nombre total de créneaux souhaités", 2, 5, 3, key="max_align")
    isolated_spec = st.selectbox("Isoler un cours 'lourd' sur un créneau autonome ?", [None] + all_specs_from_file, key="iso_spec")
    
    st.header("3. Précision")
    num_iterations = st.select_slider("Précision de la recherche", [10, 50, 100, 200, 500, 1000], 100, key="num_iter")

if uploaded_file:
    file_content = uploaded_file.getvalue().decode("utf-8")
    original_student_choices = parse_student_data(file_content)

    if original_student_choices:
        st.header("Étape 0 : Diagnostic de la Complexité")
        with st.expander("Cliquez pour visualiser la difficulté du problème", expanded=True):
            tab1, tab2 = st.tabs(["Graphe des Conflits", "Matrice des Conflits"])
            with tab1: st.graphviz_chart(create_conflict_graph_dot(original_student_choices), use_container_width=True)
            with tab2: st.dataframe(create_conflict_matrix(original_student_choices), use_container_width=True)

        st.header("Étape 1 : Analyse des Effectifs & Stratégie CNED")
        initial_counts = Counter([spec for choices in original_student_choices.values() for spec in choices])
        c1, c2 = st.columns(2)
        with c1: st.markdown("**Effectifs par spécialité**"); st.dataframe(pd.DataFrame.from_dict(initial_counts, orient='index', columns=['Effectif']).sort_values('Effectif', ascending=False))
        with c2: st.markdown(f"**Groupes à planifier (capacité max: {max_capacity})**"); st.json(step1_create_groups_from_counts(initial_counts, max_capacity))
        
        cned_threshold = st.slider("Seuil d'effectif pour proposer l'externalisation", 1, 20, 5, key="cned_thresh")
        candidate_specs = sorted([spec for spec, count in initial_counts.items() if count <= cned_threshold])
        specs_to_externalize = st.multiselect("Vérifiez les spécialités à externaliser (CNED) :", all_specs_from_file, default=candidate_specs, key="cned_multi")

        st.header("Étape 2 : Lancement de l'Optimisation")
        col_btn1, col_btn2 = st.columns([3, 1])
        if col_btn1.button("Trouver la MEILLEURE Combinaison", type="primary", use_container_width=True):
            with st.spinner(f"Analyse des conflits et recherche de la meilleure solution..."):
                # ... (le reste du code est identique et devrait maintenant fonctionner)
                num_alignments_for_puzzle = max_alignments - 1 if isolated_spec else max_alignments
                if num_alignments_for_puzzle < 1: st.error("Pas assez d'alignements pour le puzzle. Augmentez le nombre total de créneaux."), st.stop()
                choices_for_planning, isolated_assign, cned_assign = {}, defaultdict(list), defaultdict(list)
                for student, choices in original_student_choices.items():
                    retained = []
                    for spec in choices:
                        if spec in specs_to_externalize: cned_assign[student].append(spec)
                        elif spec == isolated_spec: isolated_assign[student].append(spec)
                        else: retained.append(spec)
                    choices_for_planning[student] = retained
                anchor = find_anchor_triplet(choices_for_planning)
                if anchor: st.info(f"**Ancrage automatique identifié :** Le trio `{anchor[0]}`, `{anchor[1]}` et `{anchor[2]}` est le plus conflictuel. Il servira de base à la construction.")
                planning_counts = Counter(s for c in choices_for_planning.values() for s in c)
                groups_to_plan, conflicts = step1_create_groups_from_counts(planning_counts, max_capacity), build_conflict_graph(step1_create_groups_from_counts(planning_counts, max_capacity), choices_for_planning)
                best_solution = None
                for _ in range(num_iterations):
                    candidate = generate_candidate_solution(groups_to_plan, conflicts, num_alignments_for_puzzle, anchor)
                    if candidate:
                        result = evaluate_solution_performance(choices_for_planning, candidate, max_capacity)
                        if not best_solution or result['kpis']['score'] > best_solution['kpis']['score']: best_solution = result
                if best_solution:
                    for student, specs in cned_assign.items(): best_solution['dropped_courses'].append({'Élève': student, 'Option non placée': spec, 'Raison': 'Externalisé (CNED)'})
                    for student, specs in isolated_assign.items(): best_solution['dropped_courses'].append({'Élève': student, 'Option non placée': spec, 'Raison': 'Cours Autonome'})
                    isolated_groups = step1_create_groups_from_counts({isolated_spec: len(isolated_assign)}, max_capacity) if isolated_spec else []
                    best_solution['isolated_groups'], best_solution['cned_assign'], best_solution['isolated_assign'] = isolated_groups, cned_assign, isolated_assign
                    st.session_state.solutions.append(best_solution)
                    st.success("Proposition optimale trouvée et ajoutée à l'historique !")
                else:
                    st.error("Aucune solution trouvée. Les contraintes sont trop fortes. Essayez d'augmenter les créneaux, d'isoler un cours ou d'externaliser plus d'options.")
        if col_btn2.button("Réinitialiser", use_container_width=True):
            st.session_state.solutions = []; st.rerun()
        if st.session_state.solutions:
            st.header("Étape 3 : Historique des Propositions")
            for i, solution in reversed(list(enumerate(st.session_state.solutions))):
                display_solution(solution, i + 1)
else:
    st.info("Veuillez commencer par charger un fichier CSV pour commencer.")
