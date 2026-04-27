"""
CRCP Benthic Explorer — ArcGIS Pro Python Toolbox

Provides two geoprocessing tools:
    1. Ingest and Transform CRCP Data
    2. Publish to ArcGIS Online

Requires ArcGIS Pro with access to arcpy. The underlying pipeline logic
is in the src/ package and can also be run independently without ArcPy.
"""

import os
import sys

import arcpy

# Ensure the project root is on the path so src/ can be imported
_TOOLBOX_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_TOOLBOX_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


class Toolbox:
    def __init__(self):
        self.label = "CRCP Benthic Explorer"
        self.alias = "crcp_benthic"
        self.tools = [IngestTransformTool, PublishTool]


# ─────────────────────────────────────────────────────────────────────────────
# Tool 1: Ingest and Transform
# ─────────────────────────────────────────────────────────────────────────────

class IngestTransformTool:
    def __init__(self):
        self.label = "Ingest and Transform CRCP Data"
        self.description = (
            "Query NOAA ERDDAP for CRCP benthic cover annotations, "
            "aggregate from point-level to site-year summaries, and "
            "write the result as a Feature Class."
        )
        self.canRunInBackground = True

    def getParameterInfo(self):
        source = arcpy.Parameter(
            displayName="Source Region",
            name="source_id",
            datatype="GPString",
            parameterType="Required",
            direction="Input",
        )
        source.filter.type = "ValueList"
        source.filter.list = ["hawaii", "marianas", "samoa", "prias"]
        source.value = "hawaii"

        min_year = arcpy.Parameter(
            displayName="Minimum Year (optional)",
            name="min_year",
            datatype="GPLong",
            parameterType="Optional",
            direction="Input",
        )

        max_year = arcpy.Parameter(
            displayName="Maximum Year (optional)",
            name="max_year",
            datatype="GPLong",
            parameterType="Optional",
            direction="Input",
        )

        out_gdb = arcpy.Parameter(
            displayName="Output Geodatabase",
            name="out_gdb",
            datatype="DEWorkspace",
            parameterType="Required",
            direction="Input",
        )
        out_gdb.filter.list = ["Local Database", "Remote Database"]

        out_fc = arcpy.Parameter(
            displayName="Output Feature Class",
            name="out_fc",
            datatype="DEFeatureClass",
            parameterType="Derived",
            direction="Output",
        )

        return [source, min_year, max_year, out_gdb, out_fc]

    def execute(self, parameters, messages):
        source_id = parameters[0].valueAsText
        min_year = parameters[1].value
        max_year = parameters[2].value
        out_gdb = parameters[3].valueAsText

        from src import ingest, transform, spatial

        # Step 1: Ingest
        arcpy.SetProgressorLabel("Querying ERDDAP...")
        messages.addMessage(f"Fetching data for source: {source_id}")
        points_df = ingest.fetch_source(
            source_id,
            min_year=min_year,
            max_year=max_year,
        )
        messages.addMessage(f"Fetched {len(points_df):,} point annotations")

        # Step 2: Transform
        arcpy.SetProgressorLabel("Aggregating points → images → sites...")
        sites_df = transform.run_full_transform(points_df)
        messages.addMessage(f"Produced {len(sites_df):,} site-year records")

        # Step 3: Spatial
        arcpy.SetProgressorLabel("Building spatial features...")
        gdf = spatial.build_site_geodataframe(sites_df)
        warnings = spatial.validate_coordinates(gdf, source_id)
        for w in warnings:
            messages.addWarningMessage(w)

        # Step 4: Write to Feature Class
        arcpy.SetProgressorLabel("Writing Feature Class...")
        fc_name = f"CRCP_{source_id}_site_summary"
        out_path = os.path.join(out_gdb, fc_name)

        if arcpy.Exists(out_path):
            arcpy.management.Delete(out_path)

        gdf.to_file(os.path.join(out_gdb, f"{fc_name}.shp"), driver="ESRI Shapefile")
        messages.addMessage(f"Feature Class written to: {out_path}")

        parameters[4].value = out_path

    def updateParameters(self, parameters):
        return

    def updateMessages(self, parameters):
        return


# ─────────────────────────────────────────────────────────────────────────────
# Tool 2: Publish to ArcGIS Online
# ─────────────────────────────────────────────────────────────────────────────

class PublishTool:
    def __init__(self):
        self.label = "Publish to ArcGIS Online"
        self.description = (
            "Publish a CRCP site-summary Feature Class as a Hosted "
            "Feature Layer on ArcGIS Online."
        )
        self.canRunInBackground = True

    def getParameterInfo(self):
        in_fc = arcpy.Parameter(
            displayName="Input Feature Class",
            name="in_fc",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Input",
        )

        source_id = arcpy.Parameter(
            displayName="Source Region (for naming)",
            name="source_id",
            datatype="GPString",
            parameterType="Required",
            direction="Input",
        )
        source_id.filter.type = "ValueList"
        source_id.filter.list = ["hawaii", "marianas", "samoa", "prias"]
        source_id.value = "hawaii"

        folder = arcpy.Parameter(
            displayName="AGOL Folder",
            name="folder",
            datatype="GPString",
            parameterType="Optional",
            direction="Input",
        )
        folder.value = "CRCP_Benthic_Explorer"

        overwrite = arcpy.Parameter(
            displayName="Overwrite Existing Layer",
            name="overwrite",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input",
        )
        overwrite.value = True

        out_url = arcpy.Parameter(
            displayName="Published Layer URL",
            name="out_url",
            datatype="GPString",
            parameterType="Derived",
            direction="Output",
        )

        return [in_fc, source_id, folder, overwrite, out_url]

    def execute(self, parameters, messages):
        import geopandas as gpd
        from src import publish

        in_fc = parameters[0].valueAsText
        source_id = parameters[1].valueAsText
        folder = parameters[2].valueAsText
        overwrite = parameters[3].value

        arcpy.SetProgressorLabel("Reading Feature Class...")
        gdf = gpd.read_file(in_fc)
        messages.addMessage(f"Loaded {len(gdf):,} features")

        arcpy.SetProgressorLabel("Publishing to ArcGIS Online...")
        url = publish.publish_site_summary(
            gdf=gdf,
            source_id=source_id,
            folder=folder,
            overwrite=overwrite,
        )
        messages.addMessage(f"Published Feature Layer: {url}")
        parameters[4].value = url

    def updateParameters(self, parameters):
        return

    def updateMessages(self, parameters):
        return
