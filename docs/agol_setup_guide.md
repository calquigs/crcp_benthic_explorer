# ArcGIS Online Setup Guide

Step-by-step instructions for configuring the Feature Layer, Web Map, and
Experience Builder application after running the pipeline and publishing
data via `03_publish_to_agol.ipynb`.

---

## 1. Feature Layer Configuration

After publishing, navigate to your Feature Layer item in ArcGIS Online
(**Content → CRCP_Benthic_Explorer folder → CRCP Benthic Cover – Hawaiian Archipelago**).

### 1.1 Symbology

1. Open the Feature Layer in **Map Viewer**.
2. Click the layer name → **Style**.
3. Choose **"mean_t1_CORAL"** as the attribute to show.
4. Select **Counts and Amounts (Size)** — graduated symbols sized by coral cover %.
5. Adjust the size ramp (e.g., 4px–24px) and colour ramp (e.g., yellow → red).
6. Optionally add a secondary attribute: **"reef_zone"** with unique colours.

### 1.2 Popup Configuration

1. Click the layer → **Pop-ups** → **Enable Pop-ups**.
2. Set title to: `{site} ({obs_year})`
3. Add a **Field List** element with these fields:
   - `island`, `region_name`, `reef_zone`, `depth_bin`
   - `n_images`, `min_depth`, `max_depth`
4. Add an **Arcade expression** or **Chart** element for the cover breakdown:
   - Bar chart with fields: `mean_t1_CORAL`, `mean_t1_TURF`, `mean_t1_MA`,
     `mean_t1_CCA`, `mean_t1_SED`, `mean_t1_Other`, `mean_t1_I`, `mean_t1_SC`, `mean_t1_MF`
5. Add an **Image** element:
   - URL: `{representative_image_url}`
   - This displays the representative survey photo in the popup.

### 1.3 Time Configuration

1. In the layer settings, click **Time Settings**.
2. Enable time on the **obs_year** field.
3. Set the time type to **Instant** (each feature has a single year).
4. This enables the Time Slider widget in Experience Builder.

---

## 2. Web Map

1. **Create** → **Map** in ArcGIS Online.
2. Add the published Feature Layer.
3. Set basemap to **Oceans** (or **Imagery** for satellite context).
4. Set the default extent to the Hawaiian Archipelago.
5. Save the Web Map with a descriptive title:
   **"CRCP Benthic Cover Explorer – Hawaii"**

---

## 3. Experience Builder Application

### 3.1 Create the App

1. Go to **Experience Builder** (experience.arcgis.com).
2. Click **Create New** → choose a blank template or a template with a
   sidebar layout.
3. Connect the Web Map as the primary data source.

### 3.2 Widget Layout

Recommended layout (sidebar + main map):

```
┌──────────────────────────────────────────────────────────────┐
│  Header: "CRCP Benthic Cover Explorer – Hawaiian Archipelago"│
├────────────┬─────────────────────────────────────────────────┤
│            │                                                 │
│  FILTERS   │                    MAP                          │
│            │                                                 │
│ ┌────────┐ │             (with draw-to-select               │
│ │Island  │ │              tools in toolbar)                  │
│ └────────┘ │                                                 │
│ ┌────────┐ │                                                 │
│ │Reef    │ │                                                 │
│ │Zone    │ │                                                 │
│ └────────┘ │                                                 │
│ ┌────────┐ │                                                 │
│ │Depth   │ │                                                 │
│ │Bin     │ │                                                 │
│ └────────┘ │                                                 │
│            ├─────────────────────────────────────────────────┤
│  TIME      │                                                 │
│  SLIDER    │     COVER BREAKDOWN CHART (bar/pie)             │
│            │                                                 │
│  STATS     ├─────────────────────────────────────────────────┤
│ Sites: 523 │                                                 │
│ Images:15k │     TEMPORAL TREND CHART (line)                 │
│ Coral: 18% │     grouped by island + obs_year                │
│            │                                                 │
└────────────┴─────────────────────────────────────────────────┘
```

### 3.3 Widget Configuration

**Map Widget:**
- Connect to the Web Map.
- Enable navigation tools.
- Enable the **Select** tool in the toolbar (for draw-to-select AOI).

**Filter Widget:**
- Add three filter entries:
  1. `island` — multi-select dropdown
  2. `reef_zone` — single-select dropdown
  3. `depth_bin` — single-select dropdown
- Connect all charts to respond to these filters.

**Time Slider Widget:**
- Connect to the same data source.
- Bound to the `obs_year` time field configured in step 1.3.
- Set step size to 1 year.

**Select Widget (Draw-to-Select AOI):**
- Add the **Select** widget to the Map toolbar.
- Enable drawing tools: Rectangle, Circle, Lasso, Polygon.
- Configure it so selected features drive the charts below.

**Cover Breakdown Chart:**
- Type: **Bar chart** (horizontal).
- Category: use a static series with the tier_1 cover fields.
- Fields: `mean_t1_CORAL`, `mean_t1_TURF`, `mean_t1_MA`, `mean_t1_CCA`,
  `mean_t1_SED`, `mean_t1_Other`, `mean_t1_I`, `mean_t1_SC`, `mean_t1_MF`.
- Set to respond to: map extent, selection, and filters.
- Aggregation: **Average** (across visible/selected features).

**Temporal Trend Chart:**
- Type: **Line chart**.
- Category field: `obs_year`.
- Series: `mean_t1_CORAL` (or allow user to pick via dropdown).
- Split by: `island`.
- Aggregation: **Average**.
- This produces island-level temporal trends computed dynamically.

**Summary Statistics (Text Widget):**
- Use **Feature Info** or **Text** widget with dynamic data references:
  - `{count}` — number of features in current selection
  - `{sum:n_images}` — total images
  - `{avg:mean_t1_CORAL}` — average coral cover

### 3.4 Publish

1. Click **Publish** in Experience Builder.
2. Set sharing to **Everyone (Public)** or **Organization**.
3. Copy the app URL for the README and portfolio.

---

## 4. Credit Usage Tracking

After setup, check your credit usage in **Organization → Status**:

| Item | Expected Credits |
|------|-----------------|
| Feature Layer storage (~1 MB) | ~0.25/month |
| Experience Builder app | 0 |
| Total first month | < 1 credit |
