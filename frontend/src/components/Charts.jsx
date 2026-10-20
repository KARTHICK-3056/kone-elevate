/**
 * Recharts wrappers.
 *
 * Every chart is responsive, uses the shared palette and renders a friendly
 * empty state instead of an axis-only skeleton when it has no data.
 */

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { CHART_COLORS, recommendationStyle } from '../utils/constants';
import { formatCompact, formatNumber, humanise } from '../utils/formatters';

const AXIS = { stroke: '#8593aa', fontSize: 11 };
const GRID = { stroke: '#e2e8f0', strokeDasharray: '3 3' };

const TOOLTIP_STYLE = {
  contentStyle: {
    borderRadius: '0.5rem',
    border: '1px solid #d5dae3',
    fontSize: '0.8rem',
    boxShadow: '0 8px 30px rgba(15, 28, 51, 0.12)',
  },
};

/** Shared chart frame with a title and an empty state. */
export function ChartCard({ title, subtitle, children, hasData = true, height = 280, action }) {
  return (
    <section className="card">
      <header className="card-header">
        <div>
          <h3 className="card-title">{title}</h3>
          {subtitle ? <p className="mt-0.5 text-xs text-steel-500">{subtitle}</p> : null}
        </div>
        {action}
      </header>
      <div className="p-4" style={{ height: height + 32 }}>
        {hasData ? (
          <ResponsiveContainer width="100%" height="100%">
            {children}
          </ResponsiveContainer>
        ) : (
          <div className="flex h-full items-center justify-center text-sm text-steel-400">
            No data to display yet.
          </div>
        )}
      </div>
    </section>
  );
}

/** Donut of AI recommendation categories, coloured by the shared category palette. */
export function DispositionChart({ data = [], height = 260 }) {
  const rows = data.filter((item) => item.value > 0);
  return (
    <ChartCard
      title="Recommendation categories"
      subtitle="Latest AI-assisted recommendation per component"
      hasData={rows.length > 0}
      height={height}
    >
      <PieChart>
        <Pie
          data={rows}
          dataKey="value"
          nameKey="name"
          innerRadius="55%"
          outerRadius="82%"
          paddingAngle={2}
          label={({ name, percent }) => `${humanise(name)} ${(percent * 100).toFixed(0)}%`}
          labelLine={false}
        >
          {rows.map((entry) => (
            <Cell
              key={entry.name}
              fill={recommendationStyle(entry.name)?.hex || '#8593aa'}
              stroke="#fff"
              strokeWidth={2}
            />
          ))}
        </Pie>
        <Tooltip {...TOOLTIP_STYLE} formatter={(value) => [formatNumber(value), 'Components']} />
        <Legend
          verticalAlign="bottom"
          height={28}
          iconType="circle"
          wrapperStyle={{ fontSize: 12 }}
          formatter={(value) => humanise(value)}
        />
      </PieChart>
    </ChartCard>
  );
}

/** Health-score histogram. */
export function HealthDistributionChart({ data = [], height = 260 }) {
  const colours = ['#d93025', '#f06423', '#f4a300', '#34a853', '#0f9d58'];
  return (
    <ChartCard
      title="Health score distribution"
      subtitle="Components per 20-point health band"
      hasData={data.some((item) => item.value > 0)}
      height={height}
    >
      <BarChart data={data} margin={{ top: 8, right: 8, bottom: 4, left: -18 }}>
        <CartesianGrid {...GRID} vertical={false} />
        <XAxis dataKey="name" {...AXIS} tickLine={false} />
        <YAxis {...AXIS} tickLine={false} axisLine={false} allowDecimals={false} />
        <Tooltip {...TOOLTIP_STYLE} formatter={(value) => [formatNumber(value), 'Components']} />
        <Bar dataKey="value" radius={[6, 6, 0, 0]}>
          {data.map((entry, index) => (
            <Cell key={entry.name} fill={colours[index % colours.length]} />
          ))}
        </Bar>
      </BarChart>
    </ChartCard>
  );
}

/** Horizontal bar of components by type. */
export function ComponentTypeChart({ data = [], height = 300 }) {
  return (
    <ChartCard
      title="Components by type"
      subtitle="Fleet composition"
      hasData={data.length > 0}
      height={height}
    >
      <BarChart data={data} layout="vertical" margin={{ top: 4, right: 16, bottom: 4, left: 24 }}>
        <CartesianGrid {...GRID} horizontal={false} />
        <XAxis type="number" {...AXIS} tickLine={false} allowDecimals={false} />
        <YAxis type="category" dataKey="name" width={92} {...AXIS} tickLine={false} axisLine={false} />
        <Tooltip {...TOOLTIP_STYLE} formatter={(value) => [formatNumber(value), 'Components']} />
        <Bar dataKey="value" fill="#2b406e" radius={[0, 6, 6, 0]} barSize={16} />
      </BarChart>
    </ChartCard>
  );
}

/** Lifecycle status distribution. */
export function LifecycleChart({ data = [], height = 260 }) {
  return (
    <ChartCard
      title="Lifecycle status"
      subtitle="Where components physically are today"
      hasData={data.length > 0}
      height={height}
    >
      <PieChart>
        <Pie data={data} dataKey="value" nameKey="name" outerRadius="80%" paddingAngle={2}>
          {data.map((entry, index) => (
            <Cell key={entry.name} fill={CHART_COLORS[index % CHART_COLORS.length]} stroke="#fff" strokeWidth={2} />
          ))}
        </Pie>
        <Tooltip {...TOOLTIP_STYLE} formatter={(value) => [formatNumber(value), 'Components']} />
        <Legend verticalAlign="bottom" height={40} iconType="circle" wrapperStyle={{ fontSize: 11 }} />
      </PieChart>
    </ChartCard>
  );
}

/** Prototype recovery value by component type. */
export function RecoveryValueChart({ data = [], currencySymbol = 'Rs.', height = 300 }) {
  return (
    <ChartCard
      title="Recovery value by component type"
      subtitle={`Prototype estimate, ${currencySymbol}`}
      hasData={data.length > 0}
      height={height}
    >
      <BarChart data={data} margin={{ top: 8, right: 8, bottom: 40, left: -8 }}>
        <CartesianGrid {...GRID} vertical={false} />
        <XAxis dataKey="name" {...AXIS} tickLine={false} angle={-30} textAnchor="end" height={60} />
        <YAxis {...AXIS} tickLine={false} axisLine={false} tickFormatter={formatCompact} />
        <Tooltip
          {...TOOLTIP_STYLE}
          formatter={(value) => [`${currencySymbol} ${formatNumber(value)}`, 'Recovery value']}
        />
        <Bar dataKey="value" fill="#0f9d58" radius={[6, 6, 0, 0]} barSize={26} />
      </BarChart>
    </ChartCard>
  );
}

/** Monthly service events and AI assessments. */
export function MonthlyActivityChart({ data = [], height = 280 }) {
  return (
    <ChartCard
      title="Monthly activity"
      subtitle="Service events recorded and AI assessments run"
      hasData={data.length > 0}
      height={height}
    >
      <LineChart data={data} margin={{ top: 8, right: 8, bottom: 4, left: -18 }}>
        <CartesianGrid {...GRID} vertical={false} />
        <XAxis dataKey="month" {...AXIS} tickLine={false} />
        <YAxis {...AXIS} tickLine={false} axisLine={false} allowDecimals={false} />
        <Tooltip {...TOOLTIP_STYLE} />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        <Line
          type="monotone"
          dataKey="service_events"
          name="Service events"
          stroke="#2b406e"
          strokeWidth={2}
          dot={false}
        />
        <Line
          type="monotone"
          dataKey="assessments"
          name="AI assessments"
          stroke="#0aa2c0"
          strokeWidth={2}
          dot={false}
        />
      </LineChart>
    </ChartCard>
  );
}

/** Model confidence histogram. */
export function ConfidenceChart({ data = [], height = 260 }) {
  return (
    <ChartCard
      title="Recommendation confidence"
      subtitle="Distribution of model confidence across stored assessments"
      hasData={data.some((item) => item.value > 0)}
      height={height}
    >
      <BarChart data={data} margin={{ top: 8, right: 8, bottom: 4, left: -18 }}>
        <CartesianGrid {...GRID} vertical={false} />
        <XAxis dataKey="name" {...AXIS} tickLine={false} />
        <YAxis {...AXIS} tickLine={false} axisLine={false} allowDecimals={false} />
        <Tooltip {...TOOLTIP_STYLE} formatter={(value) => [formatNumber(value), 'Assessments']} />
        <Bar dataKey="value" fill="#0aa2c0" radius={[6, 6, 0, 0]} />
      </BarChart>
    </ChartCard>
  );
}

/** Global feature importance from the trained Random Forest (Gini). */
export function FeatureImportanceChart({ data = [], height = 340 }) {
  const rows = data.slice(0, 10).map((item) => ({
    name: item.label || item.feature,
    value: Number((item.importance * 100).toFixed(2)),
  }));
  return (
    <ChartCard
      title="Model feature importance (Gini)"
      subtitle="Random Forest Gini importance, global not per-prediction. See the Prediction page for per-assessment SHAP attribution."
      hasData={rows.length > 0}
      height={height}
    >
      <BarChart data={rows} layout="vertical" margin={{ top: 4, right: 24, bottom: 4, left: 40 }}>
        <CartesianGrid {...GRID} horizontal={false} />
        <XAxis type="number" {...AXIS} tickLine={false} unit="%" />
        <YAxis type="category" dataKey="name" width={140} {...AXIS} tickLine={false} axisLine={false} />
        <Tooltip {...TOOLTIP_STYLE} formatter={(value) => [`${value}%`, 'Importance']} />
        <Bar dataKey="value" fill="#0aa2c0" radius={[0, 6, 6, 0]} barSize={14} />
      </BarChart>
    </ChartCard>
  );
}

/**
 * Forecast removals per quarter, stacked by group (component type / site /
 * region). Each series is the expected count - the sum of per-component
 * probabilities - not a count of thresholded predictions.
 */
export function ForecastRemovalsChart({ groups = [], quarters = [], height = 320 }) {
  const rows = quarters.map((quarter, index) => {
    const row = { quarter };
    groups.forEach((group) => {
      const value = group.quarters[index]?.expected_removals ?? 0;
      if (value > 0) row[group.group] = Number(value.toFixed(2));
    });
    return row;
  });
  const series = groups
    .filter((group) => group.expected_removals_total > 0)
    .map((group) => group.group);

  return (
    <ChartCard
      title="Forecast removals by quarter"
      subtitle="Expected components no longer suitable to continue using, stacked by group"
      hasData={series.length > 0}
      height={height}
    >
      <BarChart data={rows} margin={{ top: 8, right: 16, bottom: 4, left: 4 }}>
        <CartesianGrid {...GRID} vertical={false} />
        <XAxis dataKey="quarter" {...AXIS} tickLine={false} />
        <YAxis {...AXIS} tickLine={false} allowDecimals />
        <Tooltip {...TOOLTIP_STYLE} formatter={(value, name) => [value, name]} />
        <Legend verticalAlign="bottom" height={28} iconType="circle" wrapperStyle={{ fontSize: 11 }} />
        {series.map((name, index) => (
          <Bar
            key={name}
            dataKey={name}
            stackId="removals"
            fill={CHART_COLORS[index % CHART_COLORS.length]}
            radius={index === series.length - 1 ? [4, 4, 0, 0] : undefined}
          />
        ))}
      </BarChart>
    </ChartCard>
  );
}

/**
 * Component-recovery workshop capacity utilisation per quarter. Bars turn red above 100% -
 * the point at which forecast intake exceeds what the workshop can absorb.
 */
export function CapacityUtilisationChart({ quarters = [], height = 300 }) {
  const rows = quarters.map((quarter) => ({
    quarter: quarter.quarter,
    utilisation: quarter.utilisation_percent,
    hours: quarter.recovery_hours_required,
    over: quarter.over_capacity,
  }));

  return (
    <ChartCard
      title="Component-recovery capacity utilisation"
      subtitle="Forecast hours plus existing backlog against declared capacity - red is over capacity"
      hasData={rows.length > 0}
      height={height}
    >
      <ComposedChart data={rows} margin={{ top: 8, right: 16, bottom: 4, left: 4 }}>
        <CartesianGrid {...GRID} vertical={false} />
        <XAxis dataKey="quarter" {...AXIS} tickLine={false} />
        <YAxis {...AXIS} tickLine={false} unit="%" />
        <Tooltip
          {...TOOLTIP_STYLE}
          formatter={(value, name) =>
            name === 'utilisation' ? [`${value}%`, 'Utilisation'] : [value, name]
          }
        />
        <ReferenceLine
          y={100}
          stroke="#d93025"
          strokeDasharray="5 5"
          label={{ value: 'Capacity', fill: '#d93025', fontSize: 11, position: 'right' }}
        />
        <Bar dataKey="utilisation" radius={[4, 4, 0, 0]} barSize={44}>
          {rows.map((row) => (
            <Cell key={row.quarter} fill={row.over ? '#d93025' : '#0f9d58'} />
          ))}
        </Bar>
      </ComposedChart>
    </ChartCard>
  );
}

/**
 * Calibration reliability diagram: mean predicted confidence vs. observed
 * accuracy, per confidence bin. A point on the dashed diagonal means "when
 * the model said X% confident, it was right X% of the time" - the property
 * CalibratedClassifierCV is fitted to achieve. Points below the diagonal are
 * overconfident bins; above it, underconfident.
 */
export function ReliabilityDiagramChart({ bins = [], height = 320 }) {
  const rows = bins
    .filter((bin) => bin.count > 0)
    .map((bin) => ({
      confidence: bin.mean_confidence,
      accuracy: bin.observed_accuracy,
      count: bin.count,
      range: `${Math.round(bin.bin_low * 100)}-${Math.round(bin.bin_high * 100)}%`,
    }));
  const diagonal = [
    { confidence: 0, accuracy: 0 },
    { confidence: 1, accuracy: 1 },
  ];

  return (
    <ChartCard
      title="Calibration reliability diagram"
      subtitle="Perfectly calibrated points sit on the dashed diagonal"
      hasData={rows.length > 0}
      height={height}
    >
      <ComposedChart margin={{ top: 8, right: 16, bottom: 4, left: 4 }}>
        <CartesianGrid {...GRID} />
        <XAxis
          type="number"
          dataKey="confidence"
          domain={[0, 1]}
          tickFormatter={(value) => `${Math.round(value * 100)}%`}
          name="Mean confidence"
          {...AXIS}
        />
        <YAxis
          type="number"
          dataKey="accuracy"
          domain={[0, 1]}
          tickFormatter={(value) => `${Math.round(value * 100)}%`}
          name="Observed accuracy"
          {...AXIS}
        />
        <Tooltip
          {...TOOLTIP_STYLE}
          formatter={(value, name) => [`${(value * 100).toFixed(1)}%`, name]}
          labelFormatter={() => ''}
        />
        <Line
          data={diagonal}
          dataKey="accuracy"
          stroke="#c7cdd6"
          strokeWidth={2}
          strokeDasharray="5 5"
          dot={false}
          activeDot={false}
          isAnimationActive={false}
          legendType="none"
          name="Perfect calibration"
        />
        <Scatter data={rows} dataKey="accuracy" fill="#1a73e8" name="Observed accuracy" />
      </ComposedChart>
    </ChartCard>
  );
}

/** Radar view of health bands - a quick portfolio condition fingerprint. */
export function HealthBandRadar({ data = [], height = 280 }) {
  return (
    <ChartCard
      title="Portfolio condition profile"
      subtitle="Components per qualitative health band"
      hasData={data.some((item) => item.value > 0)}
      height={height}
    >
      <RadarChart data={data} outerRadius="72%">
        <PolarGrid stroke="#e2e8f0" />
        <PolarAngleAxis dataKey="name" tick={{ fill: '#66758f', fontSize: 11 }} />
        <PolarRadiusAxis tick={{ fill: '#8593aa', fontSize: 10 }} />
        <Tooltip {...TOOLTIP_STYLE} formatter={(value) => [formatNumber(value), 'Components']} />
        <Radar name="Components" dataKey="value" stroke="#2b406e" fill="#2b406e" fillOpacity={0.35} />
      </RadarChart>
    </ChartCard>
  );
}

/* -------------------------------------------------------------------------- */
/* Compliance (ESRS E5)                                                        */
/* -------------------------------------------------------------------------- */

/** Resource inflows and outflows side by side, in tonnes, by material. */
export function MaterialFlowChart({ inflows = {}, outflows = {}, height = 300 }) {
  const materials = Array.from(
    new Set([...Object.keys(inflows), ...Object.keys(outflows)]),
  );
  const rows = materials.map((material) => ({
    material,
    Inflow: inflows[material]?.tonnes ?? 0,
    Outflow: outflows[material]?.tonnes ?? 0,
  }));

  return (
    <ChartCard
      title="Material flows by material"
      subtitle="ESRS E5-4 inflows against E5-5 outflows, in tonnes"
      hasData={rows.length > 0}
      height={height}
    >
      <BarChart data={rows} margin={{ top: 8, right: 16, bottom: 4, left: 4 }}>
        <CartesianGrid {...GRID} vertical={false} />
        <XAxis dataKey="material" {...AXIS} tickLine={false} />
        <YAxis {...AXIS} tickLine={false} unit=" t" />
        <Tooltip {...TOOLTIP_STYLE} formatter={(value) => [`${value} t`, '']} />
        <Legend verticalAlign="bottom" height={28} iconType="circle" wrapperStyle={{ fontSize: 11 }} />
        <Bar dataKey="Inflow" fill="#2b406e" radius={[4, 4, 0, 0]} />
        <Bar dataKey="Outflow" fill="#12a594" radius={[4, 4, 0, 0]} />
      </BarChart>
    </ChartCard>
  );
}

/**
 * E5-5 treatment routes. Routes directed to disposal are red: the split
 * between diverted and directed is the number the disclosure turns on.
 */
export function TreatmentRouteChart({ routes = {}, height = 280 }) {
  const rows = Object.values(routes).map((route) => ({
    route: humanise(route.route),
    tonnes: route.tonnes,
    diverted: route.treatment === 'diverted_from_disposal',
  }));

  return (
    <ChartCard
      title="Outflows by treatment route"
      subtitle="ESRS E5-5. Red bars are directed to disposal; green are diverted from it"
      hasData={rows.length > 0}
      height={height}
    >
      <BarChart data={rows} layout="vertical" margin={{ top: 8, right: 24, bottom: 4, left: 8 }}>
        <CartesianGrid {...GRID} horizontal={false} />
        <XAxis type="number" {...AXIS} tickLine={false} unit=" t" />
        <YAxis type="category" dataKey="route" {...AXIS} tickLine={false} width={150} />
        <Tooltip {...TOOLTIP_STYLE} formatter={(value) => [`${value} t`, 'Mass']} />
        <Bar dataKey="tonnes" radius={[0, 4, 4, 0]}>
          {rows.map((row) => (
            <Cell key={row.route} fill={row.diverted ? '#10b981' : '#ef4444'} />
          ))}
        </Bar>
      </BarChart>
    </ChartCard>
  );
}

/** Critical raw materials by substance, in kilograms. */
export function CriticalRawMaterialsChart({ bySubstance = {}, height = 280 }) {
  const rows = Object.entries(bySubstance)
    .map(([substance, values]) => ({ substance, kg: values.kg }))
    .filter((row) => row.kg > 0);

  return (
    <ChartCard
      title="Critical raw materials"
      subtitle="EU CRM Act listed substances, by mass. Prototype estimate from material averages"
      hasData={rows.length > 0}
      height={height}
    >
      <BarChart data={rows} layout="vertical" margin={{ top: 8, right: 24, bottom: 4, left: 8 }}>
        <CartesianGrid {...GRID} horizontal={false} />
        <XAxis type="number" {...AXIS} tickLine={false} unit=" kg" />
        <YAxis type="category" dataKey="substance" {...AXIS} tickLine={false} width={150} />
        <Tooltip {...TOOLTIP_STYLE} formatter={(value) => [`${value} kg`, 'Mass']} />
        <Bar dataKey="kg" fill="#f59e0b" radius={[0, 4, 4, 0]} />
      </BarChart>
    </ChartCard>
  );
}
