<h1>CurbFlow AI: Bias-Aware Parking Enforcement Intelligence</h1>

<p><strong>Temporary submission README draft.</strong> This file uses explicit HTML heading tags inside Markdown so platforms that do not recognize <code>#</code>, <code>##</code>, and <code>###</code> still understand the document structure.</p>

<p>Most parking dashboards show where challans were issued. <strong>CurbFlow shows where enforcement should look next.</strong></p>

<p>CurbFlow AI is a full-stack parking enforcement intelligence system for the theme <strong>Poor Visibility on Parking-Induced Congestion</strong>. The core idea is simple: police challan data is not the same as ground-truth illegal parking data. It is also a record of where, when, and how enforcement was visible.</p>

<p>That distinction matters. If patrols are concentrated in morning windows or repeated station routes, then low evening challan counts can look like safety even when they are actually silence. CurbFlow separates <strong>observed violation intensity</strong> from <strong>enforcement exposure</strong>, so the system can distinguish a genuinely lower-risk zone from a zone that simply did not receive enough enforcement visibility.</p>

<h2>Dataset Used</h2>

<p>CurbFlow uses only the Theme 1 police parking violation CSV dataset.</p>

<table>
  <thead>
    <tr>
      <th>Audit Item</th>
      <th align="right">Value</th>
    </tr>
  </thead>
  <tbody>
    <tr><td>Total records</td><td align="right">298,450</td></tr>
    <tr><td>Total columns</td><td align="right">30</td></tr>
    <tr><td>Actual date range</td><td align="right">10 Nov 2023, 00:41 IST to 8 Apr 2024, 23:00 IST</td></tr>
    <tr><td>Morning records, 07:30-15:30 IST</td><td align="right">166,863</td></tr>
    <tr><td>Evening records, 15:30-20:30 IST</td><td align="right">1,386</td></tr>
    <tr><td>Morning-to-evening evidence gap</td><td align="right">120.39x</td></tr>
    <tr><td>Total 300m zones</td><td align="right">2,816</td></tr>
    <tr><td>Active zones, at least 100 records</td><td align="right">455</td></tr>
    <tr><td>Records covered by active zones</td><td align="right">259,541</td></tr>
    <tr><td>Top 10 zone concentration</td><td align="right">18.6%</td></tr>
    <tr><td>Top 1% zone concentration</td><td align="right">34.2%</td></tr>
    <tr><td>SCITA readiness</td><td align="right">85.7%</td></tr>
  </tbody>
</table>

<p>The audit also found that <code>closed_datetime</code>, <code>action_taken_timestamp</code>, and <code>description</code> are fully null. CurbFlow therefore does not use them as outcome labels.</p>

<h2>The Problem</h2>

<p>A normal heatmap answers one question:</p>

<blockquote>
  <p>Where were violations recorded?</p>
</blockquote>

<p>CurbFlow answers a more operational question:</p>

<blockquote>
  <p>Where should limited enforcement resources go next, given that the data itself is biased by patrol visibility?</p>
</blockquote>

<p>This is why CurbFlow does not treat <strong>no challan</strong> as <strong>no illegal parking</strong>. It treats it as one of three possibilities:</p>

<table>
  <thead>
    <tr>
      <th>Signal</th>
      <th>Meaning</th>
    </tr>
  </thead>
  <tbody>
    <tr><td>High challans, high exposure</td><td>Confirmed observed hotspot</td></tr>
    <tr><td>Low challans, high exposure</td><td>More likely lower operational priority</td></tr>
    <tr><td>Low challans, low exposure</td><td>Possible blindspot requiring audit patrol</td></tr>
  </tbody>
</table>

<h2>What CurbFlow Builds</h2>

<p>CurbFlow converts raw challan records into a bias-aware enforcement intelligence layer.</p>

<h3>Core Intelligence Layers</h3>

<table>
  <thead>
    <tr>
      <th>Layer</th>
      <th>What It Does</th>
    </tr>
  </thead>
  <tbody>
    <tr><td>PFDI scoring</td><td>Computes Parking-Induced Flow Disruption Index from violation severity, vehicle obstruction, location criticality, repeat behavior, and evidence confidence.</td></tr>
    <tr><td>300m zoning</td><td>Aggregates row-level violations into operational map zones.</td></tr>
    <tr><td>Enforcement visibility</td><td>Estimates where police enforcement was actually visible using device activity, user activity, station-hour activity, validation coverage, SCITA success, and patrol route patterns.</td></tr>
    <tr><td>Blindspot detection</td><td>Finds high-potential obstruction zones with low enforcement visibility, especially in evening windows.</td></tr>
    <tr><td>Patrol digital twin</td><td>Reconstructs aggregate patrol transition patterns without exposing raw device or user IDs.</td></tr>
    <tr><td>Planner</td><td>Recommends station-wise enforcement actions under officer and tow-unit constraints.</td></tr>
  </tbody>
</table>

<h2>Model Stack</h2>

<h3>1. BE-STHGT: Bias-Exposure Spatio-Temporal Heterogeneous Graph Transformer</h3>

<p>A PyTorch graph-transformer model that learns latent parking-risk signals across zones, time windows, police stations, patrol transitions, repeat-vehicle persistence, road corridors, junction basins, and exposure gaps.</p>

<h3>2. LightGBM LambdaRank</h3>

<p>A station-window ranking model that converts engineered features into deployable enforcement priority.</p>

<h3>3. Rule Blindspot Score</h3>

<p>A conservative operational prior that preserves blindspot audit signals where evening data is too sparse for pure supervised learning.</p>

<p>The deep model follows the principle that observed intensity should be exposure-aware:</p>

<pre><code>observed_mu = latent_risk * enforcement_exposure</code></pre>

<p>This prevents the model from learning the wrong lesson from low-enforcement windows.</p>

<p>The architecture is inspired by modern spatio-temporal graph-transformer traffic research, especially work showing that traffic patterns vary across both regions and time slots: <a href="https://arxiv.org/abs/2408.10822">Navigating Spatio-Temporal Heterogeneity: A Graph Transformer Approach for Traffic Forecasting</a>.</p>

<h2>Model and Planner Comparison</h2>

<p>CurbFlow is evaluated with chronological train/validation/test splits. No random split is used.</p>

<h3>Ranking and Planner Results</h3>

<table>
  <thead>
    <tr>
      <th>Method</th>
      <th align="right">Test Precision@5</th>
      <th align="right">Test Precision@10</th>
      <th align="right">Test NDCG@5</th>
      <th align="right">Test NDCG@10</th>
      <th align="right">Station-wise Precision@5</th>
    </tr>
  </thead>
  <tbody>
    <tr><td>Historical PFDI baseline</td><td align="right">0.600</td><td align="right">0.600</td><td align="right">0.188</td><td align="right">0.232</td><td align="right">0.673</td></tr>
    <tr><td>Count-only baseline</td><td align="right">0.600</td><td align="right">0.500</td><td align="right">0.675</td><td align="right">0.593</td><td align="right">0.700</td></tr>
    <tr><td>Rule blindspot baseline</td><td align="right">0.200</td><td align="right">0.200</td><td align="right">0.536</td><td align="right">0.382</td><td align="right">0.554</td></tr>
    <tr><td>LightGBM LambdaRank</td><td align="right">0.600</td><td align="right">0.800</td><td align="right">0.723</td><td align="right">0.739</td><td align="right">0.723</td></tr>
    <tr><td>CurbFlow Conservative Planner</td><td align="right">0.800</td><td align="right">0.700</td><td align="right">0.757</td><td align="right">0.723</td><td align="right">0.673</td></tr>
    <tr><td>CurbFlow Balanced Planner</td><td align="right">0.800</td><td align="right">0.700</td><td align="right">0.688</td><td align="right">0.608</td><td align="right">0.677</td></tr>
    <tr><td>CurbFlow Discovery Planner</td><td align="right">0.800</td><td align="right">0.600</td><td align="right">0.614</td><td align="right">0.473</td><td align="right">0.677</td></tr>
  </tbody>
</table>

<p>The strongest operational result is the planner shortlist: <strong>CurbFlow reaches 0.800 Precision@5 on the test split</strong>, which means the top few recommended zones are meaningfully stronger than a simple historical heatmap.</p>

<h3>BE-STHGT Deep Model Metrics</h3>

<p>The deep BE-STHGT model is used differently from a plain ranker. Its role is exposure-aware latent risk modeling and calibration.</p>

<table>
  <thead>
    <tr>
      <th>BE-STHGT Test Metric</th>
      <th align="right">Value</th>
    </tr>
  </thead>
  <tbody>
    <tr><td>Hotspot AUC</td><td align="right">0.931</td></tr>
    <tr><td>Precision@5</td><td align="right">0.600</td></tr>
    <tr><td>Precision@10</td><td align="right">0.800</td></tr>
    <tr><td>MAE PFDI</td><td align="right">73.70</td></tr>
    <tr><td>WAPE Count</td><td align="right">0.908</td></tr>
    <tr><td>Historical same-slot MAE baseline</td><td align="right">79.31</td></tr>
    <tr><td>Last-week same-slot MAE baseline</td><td align="right">94.17</td></tr>
  </tbody>
</table>

<h2>Why This Is Not Just a Heatmap</h2>

<p>A heatmap shows concentration. CurbFlow shows decision context.</p>

<table>
  <thead>
    <tr>
      <th>Basic Heatmap</th>
      <th>CurbFlow AI</th>
    </tr>
  </thead>
  <tbody>
    <tr><td>Shows recorded challans</td><td>Separates observed risk from enforcement visibility</td></tr>
    <tr><td>Treats missing records as low activity</td><td>Treats low-exposure zeroes as low evidence</td></tr>
    <tr><td>Cannot explain patrol bias</td><td>Computes patrol myopia and route coverage</td></tr>
    <tr><td>No station-wise planning</td><td>Recommends actions under officer and tow constraints</td></tr>
    <tr><td>No future learning loop</td><td>Stores deployment feedback for future action-effectiveness learning</td></tr>
  </tbody>
</table>

<h2>Operational Outputs</h2>

<p>CurbFlow surfaces three main map layers.</p>

<table>
  <thead>
    <tr>
      <th>Layer</th>
      <th>Meaning</th>
    </tr>
  </thead>
  <tbody>
    <tr><td>Observed Hotspots</td><td>High-confidence zones with strong recorded parking-disruption evidence</td></tr>
    <tr><td>Blindspots</td><td>High static obstruction potential but weak enforcement visibility</td></tr>
    <tr><td>Enforcement Planner</td><td>Action recommendations balancing known hotspots and under-covered audit zones</td></tr>
  </tbody>
</table>

<p>Recommended actions include beat patrol, towing support, mobile camera patrol, repeat-offender checks, temporary cones, evening audit patrols, patrol expansion, and evidence-quality audits.</p>

<h2>Guardrails</h2>

<p>CurbFlow is intentionally careful about its claims.</p>

<ul>
  <li>PFDI is a proxy for parking-induced flow disruption, not measured speed loss.</li>
  <li>The system does not claim measured congestion reduction.</li>
  <li>No challan does not mean no illegal parking.</li>
  <li>Evening blindspot outputs are audit priorities, not validated evening predictions.</li>
  <li>Missing validation status is treated as unknown confidence, not rejection.</li>
  <li>Repeat-pressure features use past vehicle history only.</li>
  <li>Train, validation, and test splits are chronological.</li>
  <li>Raw vehicle numbers, device IDs, and user IDs are not exposed in the API or dashboard.</li>
  <li>ASTraM and external traffic datasets are not used.</li>
</ul>

<h2>Final Pitch</h2>

<p>CurbFlow AI turns police parking violation records into a bias-aware enforcement intelligence system. It identifies what is visible, exposes what is hidden, and recommends where limited enforcement resources should go next.</p>

<p>It does not just ask where challans happened.</p>

<p><strong>It asks where enforcement should have been.</strong></p>
