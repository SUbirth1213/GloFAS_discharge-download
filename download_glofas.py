"""Download China GloFAS V5.0 consolidated daily data, one NetCDF file per year.

Credentials: ~/.cdsapirc or EWDS_API_KEY environment variable.
Run: python download_glofas.py
Runoff instead of discharge: python download_glofas.py --variable runoff
"""
import argparse
import calendar
import json
import os
from pathlib import Path
import zipfile
import shutil
import tempfile
from contextlib import contextmanager, ExitStack

import cdsapi
import numpy as np
import xarray as xr

DATASET = "cems-glofas-historical"
URL = "https://ewds.climate.copernicus.eu/api"
SYSTEM_VERSION = "version_5_0"
VARIABLES = {
    "discharge": ("average_river_discharge_in_the_last_24_hours", "time_mean"),
    "runoff": ("runoff_water_equivalent", "instantaneous"),
}


@contextmanager
def open_nc(path):
    # Some Windows netCDF4 builds cannot open Unicode filenames.
    with tempfile.TemporaryDirectory(prefix="glofas_") as work:
        local = Path(work) / "data.nc"
        shutil.copyfile(path, local)
        with xr.open_dataset(local, engine="netcdf4") as ds:
            yield ds


def check(path, year, month=None):
    with open_nc(path) as ds:
        time = next((k for k in ("time", "valid_time") if k in ds.coords and ds[k].ndim == 1), None)
        if time is None:
            raise ValueError(f"No daily time coordinate in {path}")
        dates = ds[time].values.astype("datetime64[D]")
        start = np.datetime64(f"{year}-{month:02d}-01" if month else f"{year}-01-01")
        end = (np.datetime64(f"{year+1}-01-01") if not month or month == 12
               else np.datetime64(f"{year}-{month+1:02d}-01"))
        expected = np.arange(start, end, dtype="datetime64[D]")
        # Time-mean discharge is labelled by the end of its 24-hour interval.
        if "avg_dis" in ds.data_vars:
            expected = expected + np.timedelta64(1, "D")
        if not np.array_equal(np.sort(dates), expected):
            raise ValueError(f"Missing or duplicate daily records in {path}")
        if not ds.data_vars:
            raise ValueError(f"No data variables in {path}")
        return time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--years", nargs="+", type=int, default=list(range(2020, 2025)))
    parser.add_argument("--variable", choices=VARIABLES, default="discharge")
    parser.add_argument("--version", choices=["version_4_0", "version_5_0"], default=SYSTEM_VERSION)
    parser.add_argument("--product-type", choices=["consolidated", "intermediate"], default="consolidated")
    parser.add_argument("--area", nargs=4, type=float, default=[54, 73, 3, 136],
                        metavar=("NORTH", "WEST", "SOUTH", "EAST"))
    parser.add_argument("--output", type=Path, default=Path(__file__).parent / "glofas_china")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    n, w, s, e = args.area
    if not (-90 <= s < n <= 90 and -180 <= w < e <= 180):
        parser.error("Invalid bounding box: use north west south east")
    variable, timespan = VARIABLES[args.variable]
    base = dict(system_version=args.version, hydrological_model="lisflood",
                product_type=args.product_type, variable=variable, timespan=timespan,
                area=args.area, data_format="netcdf", download_format="unarchived")
    if args.dry_run:
        print(json.dumps(dict(base, year=str(args.years[0]), month="01",
                              day=[f"{d:02d}" for d in range(1, 32)]), indent=2))
        return
    key = os.environ.get("EWDS_API_KEY")
    client = None
    # Keep separate output folders for each selection, avoiding accidental reuse.
    region = "_".join(f"{v:g}" for v in args.area)
    version_tag = args.version.replace('version_', 'v').removesuffix('_0')
    product_tag = '' if args.product_type == 'consolidated' else '_intermediate'
    folder = args.output / f"{version_tag}_{args.variable}_{region}{product_tag}"
    folder.mkdir(parents=True, exist_ok=True)
    for year in args.years:
        annual = folder / f"glofas_china_{args.variable}_{year}.nc"
        if annual.exists():
            check(annual, year)
            print(f"Already complete: {annual}", flush=True)
            continue
        months = []
        for month in range(1, 13):
            target = folder / f"{year}_{month:02d}.nc"
            if not target.exists():
                request = dict(base, year=str(year), month=f"{month:02d}",
                               day=[f"{d:02d}" for d in range(1, calendar.monthrange(year, month)[1]+1)])
                target.with_suffix(".request.json").write_text(json.dumps(request, indent=2), encoding="utf-8")
                partial = target.with_suffix(".download")
                if partial.exists() and partial.stat().st_size == 0:
                    # Preserve the failed artifact, but never reuse an empty download.
                    import time as clock
                    backup = partial.with_name(partial.name + f".empty-{clock.time_ns()}")
                    partial.replace(backup)
                    print(f"Empty download saved as {backup}; requesting this month again.", flush=True)
                if partial.exists():
                    print(f"Reusing downloaded file: {partial}", flush=True)
                else:
                    print(f"Downloading {year}-{month:02d}", flush=True)
                    if client is None:
                        client = cdsapi.Client(url=URL, **({"key": key} if key else {}))
                    transfer = partial.with_suffix('.transfer')
                    client.retrieve(DATASET, request).download(str(transfer))
                    if not transfer.exists() or transfer.stat().st_size == 0:
                        raise ValueError(f"Server download produced an empty file: {transfer}. Run again to retry.")
                    transfer.replace(partial)
                if zipfile.is_zipfile(partial):
                    with zipfile.ZipFile(partial) as archive:
                        names = [x for x in archive.namelist() if x.lower().endswith(".nc")]
                        if len(names) != 1:
                            raise ValueError(f"Expected one NetCDF in {partial}, found {names}")
                        with archive.open(names[0]) as src, target.with_suffix(".tmp.nc").open("wb") as dst:
                            shutil.copyfileobj(src, dst)
                    staged = target.with_suffix(".tmp.nc")
                else:
                    staged = partial
                check(staged, year, month)
                staged.replace(target)
            check(target, year, month)
            months.append(target)
        time = check(months[0], year, 1)
        with ExitStack() as stack:
            opened = [stack.enter_context(open_nc(p)) for p in months]
            opened = [ds if 'product_type' in ds.coords else ds.assign_coords(
                product_type=(time, [args.product_type] * ds.sizes[time])) for ds in opened]
            combined = xr.concat(opened, dim=time, data_vars="minimal", coords="minimal",
                                 compat="equals", join="exact").sortby(time)
            combined.attrs.update(source_dataset=DATASET, system_version=args.version,
                                  region_bbox_nwse=json.dumps(args.area),
                                  region_note="Bounding box includes areas outside China; no boundary mask applied.")
            if args.variable == "discharge":
                combined = combined.assign_coords(
                    interval_start=(time, combined[time].values - np.timedelta64(1, "D")))
                combined["interval_start"].attrs["long_name"] = "Start of 24-hour averaging interval; valid_time is interval end"
            combined['product_type'].attrs['long_name'] = 'Source product for each daily record'
            if 'intermediate' in combined.product_type.values:
                combined.attrs['product_type_note'] = 'Consult product_type coordinate for the source of each daily record.'
            encoding = {k: {"zlib": True, "complevel": 4} for k in combined.data_vars}
            with tempfile.TemporaryDirectory(prefix="glofas_year_") as work:
                staged = Path(work) / "annual.nc"
                combined.to_netcdf(staged, engine="netcdf4", encoding=encoding)
                check(staged, year)
                shutil.move(str(staged), str(annual))
        print(f"Complete: {annual}", flush=True)


if __name__ == "__main__":
    main()
