import { useState, useEffect, useCallback } from 'react'
import axios from 'axios'
import {
    LineChart, Line, BarChart, Bar,
    XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from 'recharts'

const api = axios.create({ baseURL: '', withCredentials: true })

// ── Gauge circular SVG ──────────────────────────────────────────────────────
function Gauge({ value, max = 100, label, unit = '%', color }) {
    const pct = Math.min(value / max, 1)
    const r = 36
    const circ = 2 * Math.PI * r
    const dash = pct * circ * 0.75  // 270° arc
    const gap = circ - dash

    const col = color || (pct > 0.85 ? '#ef4444' : pct > 0.6 ? '#f59e0b' : '#6366f1')

    return (
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6 }}>
            <svg width={100} height={100} viewBox="0 0 100 100">
                {/* Track */}
                <circle cx={50} cy={50} r={r} fill="none" stroke="rgba(255,255,255,0.07)"
                    strokeWidth={10} strokeDasharray={`${circ * 0.75} ${circ * 0.25}`}
                    strokeDashoffset={circ * 0.375} strokeLinecap="round" />
                {/* Value */}
                <circle cx={50} cy={50} r={r} fill="none" stroke={col}
                    strokeWidth={10} strokeDasharray={`${dash} ${gap + circ * 0.25}`}
                    strokeDashoffset={circ * 0.375} strokeLinecap="round"
                    style={{ transition: 'stroke-dasharray 0.5s ease' }} />
                <text x={50} y={46} textAnchor="middle" fill="white" fontSize={14} fontWeight={700}>
                    {typeof value === 'number' ? (Number.isInteger(value) ? value : value.toFixed(1)) : value}
                </text>
                <text x={50} y={60} textAnchor="middle" fill="rgba(255,255,255,0.5)" fontSize={9}>
                    {unit}
                </text>
            </svg>
            <span style={{ fontSize: 11, color: 'var(--text-muted)', textAlign: 'center' }}>{label}</span>
        </div>
    )
}

// ── KPI Card ────────────────────────────────────────────────────────────────
function KpiCard({ label, value, unit, sub, color = '#6366f1', icon }) {
    return (
        <div style={{
            background: 'var(--bg-elevated)', borderRadius: 10,
            border: '1px solid var(--border)', padding: '14px 18px',
            display: 'flex', flexDirection: 'column', gap: 4, flex: 1, minWidth: 120,
        }}>
            <div style={{ fontSize: 11, color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: 6 }}>
                {icon && <span>{icon}</span>}
                {label}
            </div>
            <div style={{ fontSize: 26, fontWeight: 700, color, letterSpacing: -1 }}>
                {value ?? '—'}
                {unit && <span style={{ fontSize: 13, fontWeight: 400, color: 'var(--text-muted)', marginLeft: 3 }}>{unit}</span>}
            </div>
            {sub && <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>{sub}</div>}
        </div>
    )
}

// ── Badge de estado ─────────────────────────────────────────────────────────
function StatusBadge({ code }) {
    const color = code < 300 ? '#4ade80' : code < 400 ? '#fbbf24' : '#f87171'
    return (
        <span style={{ fontSize: 10, color, fontWeight: 700, background: `${color}22`,
            padding: '1px 6px', borderRadius: 4 }}>
            {code}
        </span>
    )
}

// ── Tooltip personalizado para recharts ────────────────────────────────────
function CustomTooltip({ active, payload, label }) {
    if (!active || !payload?.length) return null
    return (
        <div style={{ background: '#1e1e2e', border: '1px solid rgba(255,255,255,0.1)',
            borderRadius: 6, padding: '8px 12px', fontSize: 11 }}>
            <div style={{ color: 'var(--text-muted)', marginBottom: 4 }}>{label}</div>
            {payload.map(p => (
                <div key={p.name} style={{ color: p.color }}>
                    {p.name}: <strong>{p.value}</strong>
                </div>
            ))}
        </div>
    )
}

// ── Componente principal ────────────────────────────────────────────────────
export default function MetricsDashboard() {
    const [data, setData] = useState(null)
    const [recent, setRecent] = useState([])
    const [loading, setLoading] = useState(true)
    const [lastUpdate, setLastUpdate] = useState(null)
    const [autoRefresh, setAutoRefresh] = useState(true)

    const fetch = useCallback(async () => {
        try {
            const [dash, rec] = await Promise.all([
                api.get('/api/metrics/dashboard').then(r => r.data),
                api.get('/api/metrics/requests/recent?seconds=120&limit=30').then(r => r.data),
            ])
            setData(dash)
            setRecent(rec)
            setLastUpdate(new Date())
        } catch (e) {
            console.error('Error fetching metrics', e)
        } finally {
            setLoading(false)
        }
    }, [])

    useEffect(() => { fetch() }, [fetch])

    useEffect(() => {
        if (!autoRefresh) return
        const id = setInterval(fetch, 5000)
        return () => clearInterval(id)
    }, [autoRefresh, fetch])

    if (loading) return (
        <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)' }}>
            Cargando métricas…
        </div>
    )

    if (!data) return (
        <div style={{ padding: 40, textAlign: 'center', color: '#f87171' }}>
            No se pudieron obtener las métricas. Verifica que el backend esté corriendo.
        </div>
    )

    const { system, summary_60s: s60, summary_300s: s300, endpoints, timeline } = data

    // Formatear timeline para recharts
    const timelineData = timeline.map((t, i) => ({
        name: i % 5 === 0 ? `${Math.round((timeline.length - i) * (300 / timeline.length))}s` : '',
        'Req': t.count,
        'Lat ms': t.avg_ms,
    }))

    return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>

            {/* ── Header con refresh ── */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                    <div style={{ fontSize: 16, fontWeight: 700 }}>Métricas del Sistema</div>
                    {lastUpdate && (
                        <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 2 }}>
                            Actualizado: {lastUpdate.toLocaleTimeString()}
                        </div>
                    )}
                </div>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                    <label style={{ fontSize: 11, color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: 5, cursor: 'pointer' }}>
                        <input type="checkbox" checked={autoRefresh} onChange={e => setAutoRefresh(e.target.checked)} />
                        Auto-refresh 5s
                    </label>
                    <button onClick={fetch} style={{
                        padding: '5px 12px', fontSize: 11, borderRadius: 6,
                        border: '1px solid var(--border)', background: 'transparent',
                        color: 'var(--text-secondary)', cursor: 'pointer',
                    }}>↻ Actualizar</button>
                </div>
            </div>

            {/* ── KPIs de requests (última hora) ── */}
            <div className="section-card">
                <div className="section-card__title" style={{ marginBottom: 12 }}>
                    Requests — último minuto
                </div>
                <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
                    <KpiCard label="Total requests" value={s60.total} icon="📊" color="#6366f1" />
                    <KpiCard label="Req/segundo" value={s60.rps} icon="⚡" color="#4ade80" />
                    <KpiCard label="Latencia promedio" value={s60.avg_ms} unit="ms" icon="⏱" color="#fbbf24" />
                    <KpiCard label="Latencia p95" value={s60.p95_ms} unit="ms" icon="📈" color="#f59e0b" />
                    <KpiCard label="Latencia p99" value={s60.p99_ms} unit="ms" icon="🎯" color="#ef4444"
                        sub="peor 1% de requests" />
                    <KpiCard label="Tasa de error" value={s60.error_rate} unit="%" icon="❌"
                        color={s60.error_rate > 5 ? '#ef4444' : '#4ade80'} sub={`${s60.errors} errores`} />
                </div>
            </div>

            {/* ── Gauges del sistema ── */}
            <div className="section-card">
                <div className="section-card__title" style={{ marginBottom: 16 }}>
                    Recursos del servidor — tiempo real
                </div>
                <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', justifyContent: 'space-around', alignItems: 'flex-start' }}>
                    <Gauge value={system.cpu.percent} label={`CPU — ${system.cpu.count} núcleos`} />
                    <Gauge value={system.ram.percent} label={`RAM — ${system.ram.used_mb} / ${system.ram.total_mb} MB`} />
                    <Gauge value={system.disk.percent} label={`Disco — ${system.disk.used_gb} / ${system.disk.total_gb} GB`} color="#a78bfa" />
                    <Gauge value={system.network.active_connections} max={100} unit="conn"
                        label="Conexiones activas" color="#38bdf8" />
                </div>
                <div style={{ display: 'flex', gap: 10, marginTop: 14, flexWrap: 'wrap' }}>
                    <div style={statPill}>RAM disponible: <b>{system.ram.available_mb} MB</b></div>
                    <div style={statPill}>Disco libre: <b>{system.disk.free_gb} GB</b></div>
                    <div style={statPill}>Req (5 min): <b>{s300.total}</b></div>
                    <div style={statPill}>RPS (5 min): <b>{s300.rps}</b></div>
                </div>
            </div>

            {/* ── Gráfica de timeline ── */}
            <div className="section-card">
                <div className="section-card__title" style={{ marginBottom: 12 }}>
                    Actividad — últimos 5 minutos
                </div>
                <ResponsiveContainer width="100%" height={200}>
                    <LineChart data={timelineData} margin={{ top: 4, right: 10, left: -20, bottom: 0 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                        <XAxis dataKey="name" tick={{ fill: 'rgba(255,255,255,0.3)', fontSize: 9 }} />
                        <YAxis yAxisId="req" tick={{ fill: 'rgba(255,255,255,0.3)', fontSize: 9 }} />
                        <YAxis yAxisId="lat" orientation="right" tick={{ fill: 'rgba(255,255,255,0.3)', fontSize: 9 }} />
                        <Tooltip content={<CustomTooltip />} />
                        <Legend wrapperStyle={{ fontSize: 11, paddingTop: 8 }} />
                        <Line yAxisId="req" type="monotone" dataKey="Req" stroke="#6366f1"
                            strokeWidth={2} dot={false} />
                        <Line yAxisId="lat" type="monotone" dataKey="Lat ms" stroke="#fbbf24"
                            strokeWidth={2} dot={false} />
                    </LineChart>
                </ResponsiveContainer>
            </div>

            {/* ── Latencia por endpoint ── */}
            {endpoints.length > 0 && (
                <div className="section-card">
                    <div className="section-card__title" style={{ marginBottom: 12 }}>
                        Latencia por endpoint — últimos 5 minutos
                    </div>
                    <ResponsiveContainer width="100%" height={Math.max(160, endpoints.length * 36)}>
                        <BarChart data={endpoints.slice(0, 10)} layout="vertical"
                            margin={{ top: 0, right: 60, left: 10, bottom: 0 }}>
                            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" horizontal={false} />
                            <XAxis type="number" tick={{ fill: 'rgba(255,255,255,0.3)', fontSize: 9 }} unit="ms" />
                            <YAxis type="category" dataKey="endpoint" width={140}
                                tick={{ fill: 'rgba(255,255,255,0.5)', fontSize: 9 }} />
                            <Tooltip content={<CustomTooltip />} />
                            <Bar dataKey="avg_ms" name="Prom ms" fill="#6366f1" radius={[0, 3, 3, 0]} />
                            <Bar dataKey="p95_ms" name="P95 ms" fill="#f59e0b" radius={[0, 3, 3, 0]} />
                        </BarChart>
                    </ResponsiveContainer>

                    {/* Tabla detallada */}
                    <div style={{ overflowX: 'auto', marginTop: 16 }}>
                        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11 }}>
                            <thead>
                                <tr style={{ borderBottom: '1px solid var(--border)' }}>
                                    {['Endpoint', 'Requests', 'Prom ms', 'P95 ms', 'Mín ms', 'Máx ms', 'Errores'].map(h => (
                                        <th key={h} style={{ padding: '6px 10px', textAlign: 'left',
                                            color: 'var(--text-muted)', fontWeight: 600 }}>{h}</th>
                                    ))}
                                </tr>
                            </thead>
                            <tbody>
                                {endpoints.map((ep, i) => (
                                    <tr key={i} style={{ borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                                        <td style={{ padding: '6px 10px', fontFamily: 'monospace', color: '#a78bfa' }}>
                                            {ep.endpoint}
                                        </td>
                                        <td style={{ padding: '6px 10px', color: 'var(--text-secondary)' }}>{ep.count}</td>
                                        <td style={{ padding: '6px 10px', color: latColor(ep.avg_ms) }}>{ep.avg_ms}</td>
                                        <td style={{ padding: '6px 10px', color: latColor(ep.p95_ms) }}>{ep.p95_ms}</td>
                                        <td style={{ padding: '6px 10px', color: '#4ade80' }}>{ep.min_ms}</td>
                                        <td style={{ padding: '6px 10px', color: '#f87171' }}>{ep.max_ms}</td>
                                        <td style={{ padding: '6px 10px', color: ep.errors > 0 ? '#f87171' : 'var(--text-muted)' }}>
                                            {ep.errors}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}

            {/* ── Últimos requests ── */}
            {recent.length > 0 && (
                <div className="section-card">
                    <div className="section-card__title" style={{ marginBottom: 12 }}>
                        Últimos requests
                    </div>
                    <div style={{ overflowX: 'auto' }}>
                        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11 }}>
                            <thead>
                                <tr style={{ borderBottom: '1px solid var(--border)' }}>
                                    {['Hora', 'Método', 'Endpoint', 'Estado', 'Latencia'].map(h => (
                                        <th key={h} style={{ padding: '6px 10px', textAlign: 'left',
                                            color: 'var(--text-muted)', fontWeight: 600 }}>{h}</th>
                                    ))}
                                </tr>
                            </thead>
                            <tbody>
                                {recent.map((r, i) => (
                                    <tr key={i} style={{ borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                                        <td style={{ padding: '5px 10px', color: 'var(--text-muted)' }}>
                                            {new Date(r.timestamp * 1000).toLocaleTimeString()}
                                        </td>
                                        <td style={{ padding: '5px 10px', color: '#38bdf8', fontWeight: 600 }}>
                                            {r.method}
                                        </td>
                                        <td style={{ padding: '5px 10px', fontFamily: 'monospace', color: 'var(--text-secondary)' }}>
                                            {r.path}
                                        </td>
                                        <td style={{ padding: '5px 10px' }}>
                                            <StatusBadge code={r.status_code} />
                                        </td>
                                        <td style={{ padding: '5px 10px', color: latColor(r.duration_ms) }}>
                                            {r.duration_ms} ms
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}

        </div>
    )
}

// ── Helpers ──────────────────────────────────────────────────────────────────
const latColor = (ms) => ms > 1000 ? '#ef4444' : ms > 300 ? '#f59e0b' : '#4ade80'

const statPill = {
    fontSize: 11, color: 'var(--text-muted)',
    background: 'rgba(255,255,255,0.04)', border: '1px solid var(--border)',
    borderRadius: 6, padding: '3px 10px',
}
