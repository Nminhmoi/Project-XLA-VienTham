"""Test cho scripts/03_spectral_ndvi_analysis.py trên raster tổng hợp có đáp án biết trước.

Chạy: python -m pytest tests -q
"""

import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from rasterio.windows import Window

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "03_spectral_ndvi_analysis.py"
spec = importlib.util.spec_from_file_location("spectral", SCRIPT)
spectral = importlib.util.module_from_spec(spec)
spec.loader.exec_module(spectral)

PX = 0.0413
SAT = 65535


def make_cog(path: Path, nir: np.ndarray, red: np.ndarray, rededge: np.ndarray,
             mask: np.ndarray, crs="EPSG:32630") -> Path:
    h, w = nir.shape
    data = np.stack([np.full((h, w), 1000, np.uint16), np.full((h, w), 1000, np.uint16),
                     red.astype(np.uint16), rededge.astype(np.uint16), nir.astype(np.uint16)])
    with rasterio.open(path, "w", driver="GTiff", height=h, width=w, count=5, dtype="uint16",
                       crs=crs, transform=from_origin(300000, 650000, PX, PX)) as dst:
        dst.write(data)
        dst.write_mask(mask.astype(np.uint8) * 255)
    return path


@pytest.fixture
def scene(tmp_path):
    """4 hàng x 10 cột. Mỗi hàng 1 lớp NDVI; thêm pixel ngoài mask, bão hòa, mẫu số 0.

    NIR = 1000 cố định, Red chọn để ra NDVI chính xác:
      hàng 0: red 200  -> NDVI 0.6667 (lớp 1)
      hàng 1: red 500  -> NDVI 0.3333 (lớp 2)
      hàng 2: red 900  -> NDVI 0.0526 (lớp 3)
      hàng 3: red 1500 -> NDVI -0.2   (lớp 4)
    """
    h, w = 4, 10
    nir = np.full((h, w), 1000)
    red = np.array([[200], [500], [900], [1500]]).repeat(w, axis=1)
    rededge = np.full((h, w), 600)          # NDRE = 400/1600 = 0.25
    mask = np.ones((h, w), bool)
    mask[:, 9] = False                      # cột cuối ngoài mask -> 4 px
    red[0, 8] = SAT                         # 1 px bão hòa (hàng lớp 1)
    nir[1, 8] = 0; red[1, 8] = 0            # 1 px mẫu số 0 (hàng lớp 2)
    path = make_cog(tmp_path / "cog.tif", nir, red, rededge, mask)
    out = tmp_path / "out"
    result = spectral.run(path, out, preview_max_side=50)
    return out, result


def test_normalized_difference_handles_zero_and_mask():
    a = np.array([[10, 0, 5]], np.uint16)
    b = np.array([[0, 0, 5]], np.uint16)
    valid = np.array([[True, True, False]])
    r = spectral.normalized_difference(a, b, valid)
    assert r[0, 0] == pytest.approx(1.0)
    assert np.isnan(r[0, 1])                # 0/0 -> NaN, không cảnh báo, không inf
    assert np.isnan(r[0, 2])                # ngoài mask
    assert r.dtype == np.float32


def test_uint16_subtraction_does_not_wrap():
    # nếu trừ trên uint16, 100 - 900 sẽ tràn thành số dương lớn
    r = spectral.normalized_difference(np.array([[100]], np.uint16), np.array([[900]], np.uint16),
                                       np.array([[True]]))
    assert r[0, 0] == pytest.approx(-0.8)


@pytest.mark.parametrize("ndvi, expected", [
    # mặc định (0.40, 0.10, -0.15): >t1 -> 1 ; (t2, t1] -> 2 ; [t3, t2] -> 3 ; <t3 -> 4
    (0.9, 1), (0.4001, 1), (0.40, 2), (0.25, 2), (0.1001, 2), (0.10, 3), (0.0, 3),
    (-0.15, 3), (-0.1501, 4), (-0.8, 4), (np.nan, 0),
])
def test_classify_default_thresholds(ndvi, expected):
    v = np.array([[ndvi]], np.float32)
    # so sánh trên float32 như dữ liệu thật
    assert spectral.classify_ndvi(v)[0, 0] == expected


@pytest.mark.parametrize("ndvi, expected", [
    (0.4501, 1), (0.45, 2), (0.20, 3), (0.0, 3), (-0.0001, 4),
])
def test_classify_custom_thresholds(ndvi, expected):
    assert spectral.classify_ndvi(np.array([[ndvi]], np.float32), (0.45, 0.20, 0.0))[0, 0] == expected


@pytest.mark.parametrize("bad", [(0.1, 0.4, -0.15), (0.4, 0.4, 0.0), (1.2, 0.1, 0.0), (0.4, 0.1, -1.5)])
def test_invalid_thresholds_rejected(bad):
    with pytest.raises(ValueError):
        spectral.validate_thresholds(bad)


def test_otsu_splits_bimodal_data():
    rng = np.random.default_rng(0)
    soil = rng.normal(-0.33, 0.05, 50_000)
    veg = rng.normal(0.45, 0.05, 50_000)
    t = spectral.otsu_threshold(np.concatenate([soil, veg]).astype(np.float32))
    assert -0.15 < t < 0.25                 # nằm giữa 2 đỉnh


def test_suggest_thresholds_ordered_with_nan():
    rng = np.random.default_rng(1)
    v = np.concatenate([rng.normal(-0.33, 0.08, 40_000), rng.normal(0.45, 0.08, 60_000),
                        [np.nan] * 100]).astype(np.float32)
    t1, t2, t3 = spectral.suggest_thresholds(v)
    assert 1 > t1 > t2 > t3 > -1
    spectral.validate_thresholds((t1, t2, t3))


def test_class_ranges_follow_thresholds():
    rng = {cid: r for cid, _, r in spectral.lulc_classes((0.42, 0.17, -0.14))}
    assert rng == {1: [0.42, 1.0], 2: [0.17, 0.42], 3: [-0.14, 0.17], 4: [-1.0, -0.14]}


def test_outputs_exist_and_are_georeferenced(scene):
    out, _ = scene
    for name in ("ndvi.tif", "ndre.tif", "lulc_class.tif", "lulc_summary.json",
                 "spectral_stats.json", "ndvi_preview.png"):
        assert (out / name).stat().st_size > 0, name
    for name, dtype in (("ndvi.tif", "float32"), ("ndre.tif", "float32"), ("lulc_class.tif", "uint8")):
        with rasterio.open(out / name) as ds:
            assert ds.dtypes[0] == dtype
            assert ds.crs.to_epsg() == 32630
            assert ds.res == pytest.approx((PX, PX))
            assert ds.shape == (4, 10)


def test_index_values_and_invalid_pixels(scene):
    out, _ = scene
    with rasterio.open(out / "ndvi.tif") as ds:
        ndvi = ds.read(1)
    with rasterio.open(out / "ndre.tif") as ds:
        ndre = ds.read(1)
    assert ndvi[0, 0] == pytest.approx(800 / 1200, abs=1e-6)
    assert ndvi[3, 0] == pytest.approx(-0.2, abs=1e-6)
    assert np.isnan(ndvi[:, 9]).all()       # ngoài mask
    assert np.isnan(ndvi[0, 8])             # bão hòa
    assert np.isnan(ndvi[1, 8])             # mẫu số 0
    assert np.nanmin(ndvi) >= -1 and np.nanmax(ndvi) <= 1
    assert ndre[2, 0] == pytest.approx(0.25, abs=1e-6)
    assert np.isnan(ndre[0, 8])             # bão hòa ở Red cũng loại khỏi NDRE (cùng tập pixel hợp lệ)


def test_lulc_raster(scene):
    out, _ = scene
    with rasterio.open(out / "lulc_class.tif") as ds:
        cls = ds.read(1)
        assert ds.nodata == 0
    assert (cls[0, :8] == 1).all() and (cls[1, :8] == 2).all()
    assert (cls[2, :9] == 3).all() and (cls[3, :9] == 4).all()
    assert cls[0, 8] == 0 and cls[1, 8] == 0 and (cls[:, 9] == 0).all()


def test_summary_schema_and_areas(scene):
    out, _ = scene
    s = json.loads((out / "lulc_summary.json").read_text(encoding="utf-8"))
    for key in ("crs", "pixel_size_m", "pixel_area_m2", "total_valid_area_ha", "classes"):
        assert key in s
    assert s["crs"] == "EPSG:32630"
    assert s["pixel_area_m2"] == pytest.approx(0.00170569)
    assert [c["id"] for c in s["classes"]] == [1, 2, 3, 4]
    for c in s["classes"]:
        assert set(c) >= {"id", "name", "ndvi_range", "pixel_count", "area_m2", "area_ha", "percent"}
    counts = [c["pixel_count"] for c in s["classes"]]
    assert counts == [8, 8, 9, 9]
    assert s["total_valid_pixel_count"] == 34
    assert s["excluded_pixel_count"] == {"outside_mask": 4, "saturated": 1, "zero_denominator": 1}
    assert sum(c["percent"] for c in s["classes"]) == pytest.approx(100, abs=0.05)
    assert sum(c["area_m2"] for c in s["classes"]) == pytest.approx(s["total_valid_area_m2"], abs=0.01)
    assert s["classes"][0]["area_m2"] == pytest.approx(8 * 0.00170569, abs=0.01)


def test_stats_file(scene):
    out, _ = scene
    st = json.loads((out / "spectral_stats.json").read_text(encoding="utf-8"))
    assert st["input"] == "cog.tif"         # không ghi đường dẫn tuyệt đối của máy cá nhân
    assert st["ndvi"]["valid_pixel_count"] == 34
    assert st["ndvi"]["min"] == pytest.approx(-0.2, abs=1e-4)
    assert st["ndvi"]["max"] == pytest.approx(0.6667, abs=1e-4)
    # px (1,8): NIR=0, Red=0 -> NDVI không xác định, nhưng RedEdge=600 -> NDRE = -600/600 = -1 (hợp lệ)
    assert st["ndre"]["valid_pixel_count"] == 35
    assert st["ndre"]["min"] == pytest.approx(-1.0, abs=1e-4)
    assert st["ndre"]["max"] == pytest.approx(0.25, abs=1e-4)


def test_preview_png_transparent_outside_mask(scene):
    import matplotlib.pyplot as plt
    out, _ = scene
    img = plt.imread(out / "ndvi_preview.png")
    assert img.shape == (4, 10, 4)
    assert (img[:, 9, 3] == 0).all()        # ngoài mask trong suốt
    assert (img[:, 0, 3] == 1).all()


def test_window_crop(tmp_path):
    h, w = 6, 6
    path = make_cog(tmp_path / "cog.tif", np.full((h, w), 1000), np.full((h, w), 200),
                    np.full((h, w), 600), np.ones((h, w), bool))
    out = tmp_path / "out"
    spectral.run(path, out, window=Window(2, 1, 3, 2), preview_max_side=50)
    with rasterio.open(out / "ndvi.tif") as ds, rasterio.open(path) as src:
        assert ds.shape == (2, 3)
        assert ds.transform.c == pytest.approx(src.transform.c + 2 * PX)
        assert ds.transform.f == pytest.approx(src.transform.f - 1 * PX)


def test_rejects_geographic_crs(tmp_path):
    a = np.full((2, 2), 1000)
    path = make_cog(tmp_path / "geo.tif", a, a, a, np.ones((2, 2), bool), crs="EPSG:4326")
    with pytest.raises(ValueError, match="CRS"):
        spectral.run(path, tmp_path / "out")


def test_cli_missing_input_returns_error(tmp_path):
    assert spectral.main(["--input", str(tmp_path / "nope.tif"), "--outdir", str(tmp_path)]) == 1


def test_cli_custom_thresholds_written_to_summary(tmp_path):
    h, w = 2, 2
    path = make_cog(tmp_path / "cog.tif", np.full((h, w), 1000), np.full((h, w), 500),
                    np.full((h, w), 600), np.ones((h, w), bool))   # NDVI = 0.3333
    out = tmp_path / "out"
    assert spectral.main(["--input", str(path), "--outdir", str(out), "--thresholds", "0.30", "0.20", "0.0"]) == 0
    s = json.loads((out / "lulc_summary.json").read_text(encoding="utf-8"))
    assert s["ndvi_thresholds"] == [0.30, 0.20, 0.0]
    assert s["classes"][0]["pixel_count"] == 4          # 0.333 > 0.30 -> lớp 1
    assert s["classes"][0]["ndvi_range"] == [0.30, 1.0]


def test_cli_suggest_thresholds_needs_ndvi(tmp_path):
    assert spectral.main(["--suggest-thresholds", "--outdir", str(tmp_path)]) == 1


def test_cli_rejects_bad_thresholds(tmp_path):
    a = np.full((2, 2), 1000)
    path = make_cog(tmp_path / "cog.tif", a, a, a, np.ones((2, 2), bool))
    assert spectral.main(["--input", str(path), "--outdir", str(tmp_path / "o"),
                          "--thresholds", "0.1", "0.4", "0.0"]) == 2
