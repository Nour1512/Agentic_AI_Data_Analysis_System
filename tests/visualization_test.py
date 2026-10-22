from pathlib import Path

from agents_schema.visualization import VisualizationRequest
from services.visualization_service import VisualizationService


def test_bar_chart():

    request = VisualizationRequest(
        request_id="test_bar_001",
        chart_type="bar",
        title="Sales by Product",
        data=[
            {"product": "Laptop", "sales": 150000},
            {"product": "Phone", "sales": 120000},
            {"product": "Tablet", "sales": 80000},
        ],
        x_axis_column="product",
        y_axis_column="sales",
    )

    service = VisualizationService()

    response = service.generate_chart(request)

    print(response)

    assert response.success is True
    assert response.chart_path is not None
    assert Path(response.chart_path).exists()
    
def test_line_chart():

    request = VisualizationRequest(
        request_id="test_line_001",
        chart_type="line",
        title="Sales Over Time",
        data=[
            {"month": "January", "sales": 100000},
            {"month": "February", "sales": 120000},
            {"month": "March", "sales": 150000},
            {"month": "April", "sales": 140000},
        ],
        x_axis_column="month",
        y_axis_column="sales",
    )

    service = VisualizationService()

    response = service.generate_chart(request)

    print(response)

    assert response.success is True
    assert response.chart_path is not None
    assert Path(response.chart_path).exists()

def test_pie_chart():

    request = VisualizationRequest(
        request_id="test_pie_001",
        chart_type="pie",
        title="Sales by Product",
        data=[
            {"product": "Laptop", "sales": 150000},
            {"product": "Phone", "sales": 120000},
            {"product": "Tablet", "sales": 80000},
        ],
        x_axis_column="product",
        y_axis_column="sales",
    )

    service = VisualizationService()

    response = service.generate_chart(request)

    print(response)

    assert response.success is True
    assert response.chart_path is not None
    assert Path(response.chart_path).exists()

def test_scatter_chart():

    request = VisualizationRequest(
        request_id="test_scatter_001",
        chart_type="scatter",
        title="Advertising Spend vs Sales",
        data=[
            {"advertising": 10000, "sales": 80000},
            {"advertising": 20000, "sales": 120000},
            {"advertising": 30000, "sales": 150000},
            {"advertising": 40000, "sales": 190000},
        ],
        x_axis_column="advertising",
        y_axis_column="sales",
    )

    service = VisualizationService()

    response = service.generate_chart(request)

    print(response)

    assert response.success is True
    assert response.chart_path is not None
    assert Path(response.chart_path).exists()
    
def test_invalid_chart_type():

    request = VisualizationRequest(
        request_id="test_invalid_001",
        chart_type="invalid",
        title="Invalid Chart",
        data=[
            {"product": "Laptop", "sales": 150000},
            {"product": "Phone", "sales": 120000},
        ],
        x_axis_column="product",
        y_axis_column="sales",
    )

    service = VisualizationService()

    response = service.generate_chart(request)

    print(response)

    assert response.success is False
    
def test_missing_column():

    request = VisualizationRequest(
        request_id="test_missing_001",
        chart_type="bar",
        title="Missing Column",
        data=[
            {"product": "Laptop", "sales": 150000},
            {"product": "Phone", "sales": 120000},
        ],
        x_axis_column="product",
        y_axis_column="revenue",
    )

    service = VisualizationService()

    response = service.generate_chart(request)

    print(response)

    assert response.success is False
    
def test_empty_data():

    request = VisualizationRequest(
        request_id="test_empty_001",
        chart_type="bar",
        title="Empty Data",
        data=[],
        x_axis_column="product",
        y_axis_column="sales",
    )

    service = VisualizationService()

    response = service.generate_chart(request)

    print(response)

    assert response.success is False