import json
from sre_parse import parse
import networkx as nx
from collections import defaultdict
def fingerprint(alert: dict) -> str:
    return f"{alert['service']}|{alert['metric']}|{alert['severity']}"

def session_groups(alerts: list[dict], gap_sec: int = 120) -> list[list[dict]]:
    """Mỗi group là 1 'session'. Session ngắt khi gap > gap_sec giây."""
    if not alerts:
        return []
    sorted_alerts = sorted(alerts, key=lambda a: a['ts'])
    groups = [[sorted_alerts[0]]]
    for alert in sorted_alerts[1:]:
        last_ts = parse(groups[-1][-1]['ts'])
        if (parse(alert['ts']) - last_ts).total_seconds() <= gap_sec:
            groups[-1].append(alert)
        else:
            groups.append([alert])
    return groups

def topology_group(alerts, graph, max_hop=2):
    """Gom alert có service cách nhau ≤ max_hop trên graph."""
    undirected = graph.to_undirected()
    by_service = defaultdict(list)
    for a in alerts:
        by_service[a['service']].append(a)

    services = list(by_service.keys())
    parent = {s: s for s in services}
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i, s1 in enumerate(services):
        for s2 in services[i+1:]:
            try:
                if nx.shortest_path_length(undirected, s1, s2) <= max_hop:
                    parent[find(s1)] = find(s2)
            except nx.NetworkXNoPath:
                pass

    groups = defaultdict(list)
    for s in services:
        groups[find(s)].extend(by_service[s])
    return list(groups.values())

def correlate(alerts, graph, gap_sec=120, max_hop=2):
    sessions = session_groups(alerts, gap_sec=gap_sec)
    clusters = []
    for s_idx, session_alerts in enumerate(sessions):
        for g_idx, group in enumerate(topology_group(session_alerts, graph, max_hop)):
            clusters.append({
                'cluster_id': f'c-{s_idx:03d}-{g_idx:03d}',
                'alert_count': len(group),
                'services': sorted({a['service'] for a in group}),
                'time_range': [min(a['ts'] for a in group), max(a['ts'] for a in group)],
                'max_severity': max(a['severity'] for a in group),
                'alert_ids': [a['id'] for a in group],
                'fingerprints': sorted(list({fingerprint(a) for a in group})),
            })
    return clusters

def build_graph_from_json(json_path):
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    G = nx.DiGraph()

    for edge in data["edges"]:
        G.add_edge(
            edge["from"],
            edge["to"],
            type=edge.get("type", "unknown")
        )

    return G