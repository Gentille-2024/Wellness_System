"""Chart specs for static/js/charts.js (rendered with Chart.js)."""


def trend_chart(trend):
    return {
        "type": "bar",
        "labels": trend["labels"],
        "datasets": [
            {"label": "Services used", "data": trend["visits"]},
            {"label": "Amount (RWF)", "data": trend["spend"], "type": "line", "axis": "money", "color": "--chart-3"},
        ],
    }


def participants_chart(trend):
    return {
        "type": "line",
        "labels": trend["labels"],
        "datasets": [{"label": "Employees who used a service", "data": trend["participants"], "color": "--chart-2"}],
        "legend": False,
    }


def company_share_chart(companies):
    return {
        "type": "doughnut",
        "labels": [c["company__name"] for c in companies],
        "datasets": [{"label": "Amount", "data": [float(c["spend"]) for c in companies]}],
        "money": True,
    }


def department_chart(departments):
    rows = [d for d in departments if d["employees"]]
    return {
        "type": "bar",
        "horizontal": True,
        "labels": [d["department"] for d in rows],
        "datasets": [{"label": "Participation (%)", "data": [float(d["participation"] or 0) for d in rows], "color": "--chart-1"}],
        "legend": False,
    }


def services_chart(labels, visits, previous, unit="month"):
    return {
        "type": "bar",
        "horizontal": True,
        "labels": labels,
        "datasets": [
            {"label": f"This {unit}", "data": visits, "color": "--chart-1"},
            {"label": f"Previous {unit}", "data": previous, "color": "--chart-2"},
        ],
    }


def indicator_chart(row):
    trend = row["trend"]
    datasets = [{"label": "Actual", "data": [t["actual"] for t in trend], "type": "line", "color": "--chart-1"}]
    if any(t["target"] is not None for t in trend):
        datasets.append({"label": "Target", "data": [t["target"] for t in trend], "type": "line", "dashed": True, "color": "--chart-3"})
    return {
        "type": "line",
        "labels": [t["month"] for t in trend],
        "datasets": datasets,
        "money": row["indicator"].unit == "money",
        "legend": len(datasets) > 1,
    }
