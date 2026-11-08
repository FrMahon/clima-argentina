from clima.heatgrid import build_cells, point_in_geometry

SQUARE = {"type": "Polygon", "coordinates": [[[0.2, 0.2], [1.8, 0.2], [1.8, 1.8], [0.2, 1.8], [0.2, 0.2]]]}

SQUARE_WITH_HOLE = {
    "type": "Polygon",
    "coordinates": [
        [[0, 0], [4, 0], [4, 4], [0, 4], [0, 0]],
        [[1, 1], [3, 1], [3, 3], [1, 3], [1, 1]],
    ],
}


def test_punto_dentro_y_fuera():
    assert point_in_geometry((1, 1), SQUARE)
    assert not point_in_geometry((3, 3), SQUARE)


def test_punto_en_un_hueco_queda_afuera():
    assert point_in_geometry((0.5, 0.5), SQUARE_WITH_HOLE)
    assert not point_in_geometry((2, 2), SQUARE_WITH_HOLE)


def test_multipolygon():
    multi = {"type": "MultiPolygon", "coordinates": [SQUARE["coordinates"], [[[5, 5], [6, 5], [6, 6], [5, 6], [5, 5]]]]}
    assert point_in_geometry((5.5, 5.5), multi)
    assert not point_in_geometry((3.5, 3.5), multi)


def test_build_cells_incluye_celdas_que_tocan_el_poligono():
    cells = build_cells(SQUARE, bbox=(-2, -2, 2, 2), step=1)
    # Las cuatro celdas entre 0 y 2 tocan el cuadrado; las de -2..0 no.
    assert sorted(cells) == [[0, 0], [0, 1], [1, 0], [1, 1]]


def test_build_cells_redondea_coordenadas():
    cells = build_cells(SQUARE, bbox=(0, 0, 2, 2), step=0.5)
    assert all(round(lon, 2) == lon and round(lat, 2) == lat for lon, lat in cells)
