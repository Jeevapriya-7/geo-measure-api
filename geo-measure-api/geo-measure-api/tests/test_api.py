import io
import zipfile

import geopandas as gpd
import pytest
from pyproj import Geod
from shapely.geometry import LineString, Point, Polygon

KML = b"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2"><Document>
 <Placemark><name>plot</name><Polygon><outerBoundaryIs><LinearRing><coordinates>
  77.70,11.34 77.71,11.34 77.71,11.35 77.70,11.35 77.70,11.34
 </coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark>
 <Placemark><name>road</name><LineString><coordinates>77.70,11.34 77.71,11.34</coordinates></LineString></Placemark>
 <Placemark><name>well</name><Point><coordinates>77.705,11.345</coordinates></Point></Placemark>
 <Placemark><name>mixed</name><MultiGeometry>
  <Point><coordinates>77.70,11.34</coordinates></Point>
  <LineString><coordinates>77.70,11.34 77.71,11.34</coordinates></LineString>
 </MultiGeometry></Placemark>
</Document></kml>"""

GEOD = Geod(ellps="WGS84")


def shapefile_zip(gdf, tmp_path, with_prj=True) -> bytes:
    gdf.to_file(tmp_path / "data.shp")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for p in tmp_path.glob("data.*"):
            if p.suffix == ".prj" and not with_prj:
                continue
            zf.write(p, p.name)
    return buf.getvalue()


def upload(client, name, data):
    return client.post("/api/files/", files={"file": (name, data)})


def test_kml_upload_and_measurements(client):
    r = upload(client, "survey.kml", KML)
    assert r.status_code == 201
    info = r.json()
    assert info["status"] == "COMPLETED"
    assert info["feature_count"] == 4
    assert info["crs"] == "EPSG:4326"
    assert client.get(f"/api/files/{info['id']}/").json()["filename"] == "survey.kml"

    feats = client.get(f"/api/files/{info['id']}/measurements/").json()["features"]
    by_type = {f["geometry_type"]: f for f in feats}

    # Compare against an independent geodesic calculation (within 0.5%)
    poly = Polygon([(77.70, 11.34), (77.71, 11.34), (77.71, 11.35), (77.70, 11.35)])
    expected_area = abs(GEOD.geometry_area_perimeter(poly)[0])
    got = by_type["Polygon"]["measurements"]
    assert got["area_sq_m"] == pytest.approx(expected_area, rel=0.005)
    assert got["projected_crs"] == "EPSG:32643"  # UTM 43N covers Erode

    expected_len = GEOD.geometry_length(LineString([(77.70, 11.34), (77.71, 11.34)]))
    assert by_type["LineString"]["measurements"]["length_m"] == pytest.approx(expected_len, rel=0.005)

    assert by_type["Point"]["measurement_status"] == "NOT_REQUIRED"
    assert by_type["GeometryCollection"]["measurement_status"] == "UNSUPPORTED"
    assert by_type["GeometryCollection"]["warnings"]


def test_shapefile_projected_crs_exact(client, tmp_path):
    gdf = gpd.GeoDataFrame(
        {"name": ["sq"]},
        geometry=[Polygon([(500000, 1255000), (500100, 1255000), (500100, 1255100), (500000, 1255100)])],
        crs="EPSG:32643",
    )
    r = upload(client, "plots.zip", shapefile_zip(gdf, tmp_path))
    assert r.status_code == 201 and r.json()["crs"] == "EPSG:32643"
    feat = client.get(f"/api/files/{r.json()['id']}/measurements/").json()["features"][0]
    assert feat["properties"]["name"] == "sq"
    assert feat["measurements"]["area_sq_m"] == pytest.approx(10000, rel=0.001)


def test_shapefile_wgs84_points_and_lines(client, tmp_path):
    gdf = gpd.GeoDataFrame({"id": [1, 2]}, geometry=[Point(77.7, 11.3), Point(77.8, 11.4)], crs="EPSG:4326")
    r = upload(client, "pts.zip", shapefile_zip(gdf, tmp_path))
    assert r.status_code == 201
    feats = client.get(f"/api/files/{r.json()['id']}/measurements/?include_geometry=false").json()["features"]
    assert all(f["measurement_status"] == "NOT_REQUIRED" and f["geometry"] is None for f in feats)


def test_shapefile_without_prj_rejected(client, tmp_path):
    gdf = gpd.GeoDataFrame({"a": [1]}, geometry=[Point(1, 1)], crs="EPSG:4326")
    r = upload(client, "noprj.zip", shapefile_zip(gdf, tmp_path, with_prj=False))
    assert r.status_code == 422
    assert "CRS" in r.json()["detail"]


def test_error_cases(client):
    assert upload(client, "a.txt", b"x").status_code == 415
    assert upload(client, "bad.kml", b"not xml").status_code == 422
    assert upload(client, "bad.zip", b"not a zip").status_code == 422
    assert client.get("/api/files/doesnotexist/").status_code == 404
    assert client.get("/api/files/..%2F..%2Fetc/").status_code in (404, 422)


def test_zip_slip_blocked(client):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("../../evil.shp", b"x")
    r = upload(client, "evil.zip", buf.getvalue())
    assert r.status_code == 422


def test_pagination_and_filter(client):
    fid = upload(client, "survey.kml", KML).json()["id"]
    r = client.get(f"/api/files/{fid}/measurements/?page_size=2&page=2").json()
    assert len(r["features"]) == 2 and r["feature_count"] == 4
    r = client.get(f"/api/files/{fid}/measurements/?geometry_type=Polygon").json()
    assert r["feature_count"] == 1
