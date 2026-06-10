import pandas as pd
import networkx as nx
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


def extract_main_alert_services(fingerprints):
    severity_scores = {}

    for fp in fingerprints:
        parts = fp.split("|")

        if len(parts) >= 3:
            svc, metric, severity = parts[0], parts[1], parts[2]
            weight = 2.0 if severity.lower() == "crit" else 1.0
            severity_scores[svc] = severity_scores.get(svc, 0.0) + weight

    if not severity_scores:
        return []

    max_score = max(severity_scores.values())

    return [
        svc for svc, score in severity_scores.items()
        if score == max_score
    ]


def run_graph_scorer(global_graph, target_services, alert_services=None):
    subgraph = global_graph.subgraph(target_services).copy()

    if len(subgraph.nodes) == 0:
        return {node: 0.0 for node in target_services}

    reversed_subgraph = subgraph.reverse(copy=True)

    if alert_services is None:
        alert_services = []

    alert_services = [
        svc for svc in alert_services
        if svc in reversed_subgraph.nodes
    ]

    if len(alert_services) == 0:
        personalization = {
            node: 1.0 / len(reversed_subgraph.nodes)
            for node in reversed_subgraph.nodes
        }
    else:
        personalization = {
            node: 1.0 / len(alert_services) if node in alert_services else 0.0
            for node in reversed_subgraph.nodes
        }

    try:
        pagerank_scores = nx.pagerank(
            reversed_subgraph,
            alpha=0.85,
            personalization=personalization,
            max_iter=1000,
            tol=1e-06
        )
    except Exception:
        pagerank_scores = nx.in_degree_centrality(reversed_subgraph)

    return {
        node: pagerank_scores.get(node, 0.0)
        for node in target_services
    }


def run_temporal_scorer(fingerprints, target_services):
    severity_scores = {node: 0.0 for node in target_services}

    for fp in fingerprints:
        parts = fp.split("|")

        if len(parts) >= 3:
            svc, metric, severity = parts[0], parts[1], parts[2]

            if svc in severity_scores:
                weight = 2.0 if severity.lower() == "crit" else 1.0
                severity_scores[svc] += weight

    max_score = max(severity_scores.values()) if severity_scores else 1.0

    if max_score == 0:
        max_score = 1.0

    return {
        svc: score / max_score
        for svc, score in severity_scores.items()
    }


def extract_top_k_candidates(cluster_json, global_graph, K=3, alpha=0.6):
    final_results = {}

    for cluster in cluster_json["clusters"]:
        cluster_id = cluster["cluster_id"]
        services = cluster["services"]
        fingerprints = cluster["fingerprints"]

        main_alert_services = extract_main_alert_services(fingerprints)

        graph_scores = run_graph_scorer(
            global_graph,
            services,
            alert_services=main_alert_services
        )

        temporal_scores = run_temporal_scorer(
            fingerprints,
            services
        )

        combined_data = []

        for svc in services:
            graph_score = graph_scores.get(svc, 0.0)
            temporal_score = temporal_scores.get(svc, 0.0)

            hybrid_score = alpha * graph_score + (1 - alpha) * temporal_score

            combined_data.append({
                "service": svc,
                "graph_score": round(graph_score, 4),
                "temporal_score": round(temporal_score, 4),
                "hybrid_score": round(hybrid_score, 4)
            })

        df_candidates = pd.DataFrame(combined_data)

        top_k = (
            df_candidates
            .sort_values(by="hybrid_score", ascending=False)
            .head(K)
        )

        final_results[cluster_id] = top_k.to_dict(orient="records")

    return final_results


def retrieve_similar_incidents(cluster_json, history_incidents, top_k=3):
    raw_fingerprints = []

    for cluster in cluster_json["clusters"]:
        raw_fingerprints.extend(cluster["fingerprints"])

    current_query = " ".join(raw_fingerprints).replace("|", " ")

    corpus = [inc["summary"] for inc in history_incidents]

    vectorizer = TfidfVectorizer(stop_words="english")
    tfidf_matrix = vectorizer.fit_transform(corpus)

    query_vector = vectorizer.transform([current_query])
    similarity_scores = cosine_similarity(query_vector, tfidf_matrix).flatten()

    results = []

    for idx, score in enumerate(similarity_scores):
        inc = history_incidents[idx].copy()
        inc["similarity_score"] = round(float(score), 4)
        results.append(inc)

    df_history = pd.DataFrame(results)

    return (
        df_history
        .sort_values(by="similarity_score", ascending=False)
        .head(top_k)
        .to_dict(orient="records")
    )


def classify_clusters_by_history(cluster_json, history_incidents):
    corpus = [inc["summary"] for inc in history_incidents]

    vectorizer = TfidfVectorizer(stop_words="english")
    tfidf_matrix = vectorizer.fit_transform(corpus)

    cluster_results = {}

    for cluster in cluster_json["clusters"]:
        cluster_id = cluster["cluster_id"]
        cluster_query = " ".join(cluster["fingerprints"]).replace("|", " ")

        query_vector = vectorizer.transform([cluster_query])
        similarity_scores = cosine_similarity(query_vector, tfidf_matrix).flatten()

        top_1_index = similarity_scores.argmax()
        max_score = similarity_scores[top_1_index]

        matched_incident = history_incidents[top_1_index]

        cluster_results[cluster_id] = {
            "matched_incident_id": matched_incident["id"],
            "similarity_score": round(float(max_score), 4),
            "predicted_class": matched_incident["root_cause_class"],
            "suspected_service": matched_incident["root_cause_service"],
            "recommended_actions": matched_incident["remediation"]
        }

    return cluster_results


def run_rca(primary_cluster, alerts, graph, history):
    """
    primary_cluster là cluster lớn nhất từ pipeline.py, không phải alert.
    Trả về đúng các key mà pipeline.py đang cần:
    - root_cause
    - confidence
    - reasoning
    - actions
    - similar_incidents
    """

    cluster_json = {
        "clusters": [primary_cluster]
    }
    print(cluster_json)

    if isinstance(history, dict):
        history_incidents = history.get("incidents", [])
    else:
        history_incidents = history

    cluster_id = primary_cluster["cluster_id"]

    # L2: Graph + severity scoring
    top_candidates = extract_top_k_candidates(
        cluster_json,
        graph,
        K=3,
        alpha=0.6
    )

    candidates = top_candidates.get(cluster_id, [])

    if candidates:
        best_candidate = candidates[0]
        root_cause_service = best_candidate["service"]
        confidence = best_candidate["hybrid_score"]
    else:
        root_cause_service = (
            primary_cluster["services"][0]
            if primary_cluster.get("services")
            else "unknown"
        )
        confidence = 0.0

    # L3: Historical incident retrieval
    similar_incidents = []
    actions = []
    historical_reason = ""

    if history_incidents:
        similar_incidents_full = retrieve_similar_incidents(
            cluster_json,
            history_incidents,
            top_k=3
        )

        similar_incidents = [
            inc.get("id")
            for inc in similar_incidents_full
            if inc.get("id")
        ]

        if similar_incidents_full:
            best_history = similar_incidents_full[0]

            if best_history.get("remediation"):
                actions.append(best_history["remediation"])

            historical_reason = (
                f"Incident lịch sử gần nhất là {best_history.get('id')} "
                f"với similarity={best_history.get('similarity_score')}."
            )

    # Nếu không có action từ history thì fallback action mặc định
    if not actions:
        actions = [
            f"Kiểm tra logs của service {root_cause_service}",
            f"Kiểm tra metric/fingerprint trong cluster {cluster_id}",
            "Kiểm tra các service upstream/downstream trong dependency graph"
        ]

    reasoning = (
        f"Primary cluster là {cluster_id} với "
        f"{primary_cluster.get('alert_count')} alerts. "
        f"Service nghi ngờ cao nhất là {root_cause_service}, "
        f"dựa trên hybrid score kết hợp PageRank graph và severity alert. "
        f"{historical_reason}"
    )

    return {
        "root_cause": root_cause_service,
        "confidence": round(float(confidence), 4),
        "reasoning": reasoning,
        "actions": actions,
        "similar_incidents": similar_incidents,
        "top_candidates": candidates
    }