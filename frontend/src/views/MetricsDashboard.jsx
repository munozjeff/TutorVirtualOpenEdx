import { useState, useEffect, useCallback, useRef } from 'react'
import axios from 'axios'
import {
    LineChart, Line, BarChart, Bar,
    XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from 'recharts'

const api = axios.create({ baseURL: '', withCredentials: true })

// ── Paleta de colores ────────────────────────────────────────────────────────
const C = {
    indigo: '#818cf8', indigoDim: 'rgba(129,140,248,0.15)',
    green:  '#4ade80', greenDim:  'rgba(74,222,128,0.15)',
    amber:  '#fbbf24', amberDim:  'rgba(251,191,36,0.15)',
    orange: '#fb923c', orangeDim: 'rgba(251,146,60,0.15)',
    red:    '#f87171', redDim:    'rgba(248,113,113,0.15)',
    blue:   '#38bdf8', blueDim:   'rgba(56,189,248,0.15)',
    violet: '#c084fc', violetDim: 'rgba(192,132,252,0.15)',
    muted:  'rgba(255,255,255,0.38)',
    dim:    'rgba(255,255,255,0.14)',
    card:   'rgba(255,255,255,0.04)',
    border: 'rgba(255,255,255,0.09)',
}

// ── Gauge circular SVG ──────────────────────────────────────────────────────
function Gauge({ value, max = 100, label, unit = '%', color }) {
    const pct = Math.min((value || 0) / max, 1)
    const r = 42, circ = 2 * Math.PI * r
    const arcLen = 0.75 * circ           // 270° de arco
    const filled = arcLen * pct
    const col = color || (pct > 0.85 ? C.red : pct > 0.60 ? C.amber : C.green)
    const display = typeof value === 'number'
        ? (value % 1 === 0 ? value : value.toFixed(1))
        : (value ?? 0)

    return (
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8, flex: 1, minWidth: 130 }}>
            <div style={{ position: 'relative', width: 120, height: 120 }}>
                <svg width={120} height={120} viewBox="0 0 100 100">
                    {/* Sombra suave */}
                    <circle cx={50} cy={50} r={r} fill="none"
                        stroke="rgba(0,0,0,0.4)" strokeWidth={13}
                        strokeDasharray={`${arcLen} ${circ - arcLen}`}
                        transform="rotate(135 50 50)" strokeLinecap="round" />
                    {/* Track (fondo del arco) */}
                    <circle cx={50} cy={50} r={r} fill="none"
                        stroke="rgba(255,255,255,0.10)" strokeWidth={11}
                        strokeDasharray={`${arcLen} ${circ - arcLen}`}
                        transform="rotate(135 50 50)" strokeLinecap="round" />
                    {/* Valor */}
                    <circle cx={50} cy={50} r={r} fill="none"
                        stroke={col} strokeWidth={11}
                        strokeDasharray={`${filled} ${circ - filled}`}
                        transform="rotate(135 50 50)" strokeLinecap="round"
                        style={{ transition: 'stroke-dasharray 0.6s ease', filter: `drop-shadow(0 0 6px ${col}88)` }} />
                    {/* Valor central */}
                    <text x={50} y={47} textAnchor="middle" fill="white" fontSize={16} fontWeight={800} letterSpacing={-0.5}>{display}</text>
                    <text x={50} y={62} textAnchor="middle" fill={C.muted} fontSize={10}>{unit}</text>
                </svg>
            </div>
            <span style={{ fontSize: 11, color: C.muted, textAlign: 'center', lineHeight: 1.3 }}>{label}</span>
        </div>
    )
}

// ── KPI Card ────────────────────────────────────────────────────────────────
function KpiCard({ label, value, unit, sub, color = C.indigo, icon }) {
    return (
        <div style={{
            background: C.card, borderRadius: 12,
            border: `1px solid ${C.border}`, padding: '16px 20px',
            display: 'flex', flexDirection: 'column', gap: 5, flex: 1, minWidth: 130,
        }}>
            <div style={{ fontSize: 11, color: C.muted, display: 'flex', alignItems: 'center', gap: 6, fontWeight: 500 }}>
                {icon && <span style={{ fontSize: 13 }}>{icon}</span>}{label}
            </div>
            <div style={{ fontSize: 30, fontWeight: 800, color, letterSpacing: -1, lineHeight: 1 }}>
                {value ?? '—'}
                {unit && <span style={{ fontSize: 14, fontWeight: 400, color: C.muted, marginLeft: 4 }}>{unit}</span>}
            </div>
            {sub && <div style={{ fontSize: 10, color: C.dim }}>{sub}</div>}
        </div>
    )
}

function StatusBadge({ code }) {
    const color = code < 300 ? C.green : code < 400 ? C.amber : C.red
    return <span style={{ fontSize: 10, color, fontWeight: 700, background: `${color}22`, padding: '2px 7px', borderRadius: 4, letterSpacing: 0.3 }}>{code}</span>
}

function CustomTooltip({ active, payload, label }) {
    if (!active || !payload?.length) return null
    return (
        <div style={{ background: '#1a1a2e', border: `1px solid ${C.border}`, borderRadius: 8, padding: '10px 14px', fontSize: 11, boxShadow: '0 4px 20px rgba(0,0,0,0.5)' }}>
            <div style={{ color: C.muted, marginBottom: 5, fontWeight: 600 }}>{label}</div>
            {payload.map(p => <div key={p.name} style={{ color: p.color, marginTop: 2 }}>{p.name}: <strong>{p.value}</strong></div>)}
        </div>
    )
}

const latColor = ms => ms > 1000 ? C.red : ms > 300 ? C.amber : C.green
const statPill = {
    fontSize: 11, color: 'rgba(255,255,255,0.7)',
    background: 'rgba(255,255,255,0.07)', border: `1px solid ${C.border}`,
    borderRadius: 6, padding: '4px 12px', fontWeight: 500,
}


// ══════════════════════════════════════════════════════════════════════════════
// Panel de Prueba de Estrés
// ══════════════════════════════════════════════════════════════════════════════
function StressTestPanel() {
    const [endpoints, setEndpoints] = useState(['/api/health'])
    const [questions, setQuestions] = useState([])
    const [form, setForm] = useState({
        scenario: 'basic',
        endpoint: '/api/health', method: 'GET',
        concurrent_users: 10, duration_seconds: 30,
        ramp_up_seconds: 5, think_time_ms: 500,
    })
    const [state, setState] = useState({ status: 'idle', progress: 0, active_users: 0, stats: {}, config: {}, sessions_ready: 0 })
    const [preparing, setPreparing] = useState(false)
    const [prepareMsg, setPrepareMsg] = useState(null)
    const pollRef = useRef(null)

    useEffect(() => {
        api.get('/api/metrics/stress-test/endpoints').then(r => setEndpoints(r.data)).catch(() => {})
        api.get('/api/metrics/stress-test/questions').then(r => setQuestions(r.data)).catch(() => {})
        pollStatus()
    }, [])

    const pollStatus = async () => {
        try {
            const r = await api.get('/api/metrics/stress-test/status')
            setState(r.data)
            if (r.data.status === 'running') {
                pollRef.current = setTimeout(pollStatus, 800)
            }
        } catch {}
    }

    const prepare = async () => {
        setPreparing(true)
        setPrepareMsg(null)
        try {
            const r = await api.post(`/api/metrics/stress-test/prepare?n=${form.concurrent_users}`)
            setPrepareMsg({ ok: true, text: `✅ ${r.data.created} sesiones creadas en "${r.data.instance}" — ${r.data.questions_pool} preguntas listas` })
            pollStatus()
        } catch (e) {
            setPrepareMsg({ ok: false, text: '❌ ' + (e.response?.data?.detail || 'Error al preparar sesiones') })
        } finally {
            setPreparing(false)
        }
    }

    const start = async () => {
        try {
            await api.post('/api/metrics/stress-test/start', form)
            pollRef.current = setTimeout(pollStatus, 500)
        } catch (e) {
            alert(e.response?.data?.detail || 'Error al iniciar la prueba')
        }
    }

    const stop = async () => {
        clearTimeout(pollRef.current)
        await api.post('/api/metrics/stress-test/stop')
        setTimeout(pollStatus, 300)
    }

    const cleanup = async () => {
        await api.post('/api/metrics/stress-test/cleanup')
        setPrepareMsg(null)
        pollStatus()
    }

    const setField = (k, v) => setForm(f => ({ ...f, [k]: v }))
    const isRunning = state.status === 'running'
    const isDone = state.status === 'done' || state.status === 'stopped'
    const pct = Math.round((state.progress || 0) * 100)
    const s = state.stats || {}
    const isRealistic = form.scenario === 'realistic'
    const sessionsReady = (state.sessions_ready || 0) > 0
    const canStart = !isRunning && (!isRealistic || sessionsReady)

    return (
        <div className="section-card" style={{ border: '1px solid rgba(239,68,68,0.3)', background: 'rgba(239,68,68,0.03)' }}>
            <div className="section-card__title" style={{ marginBottom: 14 }}>
                🔥 Prueba de Estrés
                <span style={{ fontSize: 11, fontWeight: 400, color: 'var(--text-muted)', marginLeft: 8 }}>
                    Simula usuarios concurrentes con interacciones reales de IA
                </span>
            </div>

            {/* Selector de escenario */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 14 }}>
                {[
                    {
                        key: 'basic',
                        title: '⚡ Básico',
                        desc: 'Requests directos a un endpoint sin autenticación. Mide capacidad bruta del servidor.',
                        color: '#6366f1',
                    },
                    {
                        key: 'realistic',
                        title: '🎓 Realista (IA)',
                        desc: 'Simula estudiantes reales: login → config → preguntas al chat con IA. Mide el rendimiento completo.',
                        color: '#ef4444',
                    },
                ].map(sc => (
                    <div key={sc.key} onClick={() => !isRunning && setField('scenario', sc.key)}
                        style={{
                            padding: '10px 14px', borderRadius: 8, cursor: isRunning ? 'default' : 'pointer',
                            border: `2px solid ${form.scenario === sc.key ? sc.color : 'var(--border)'}`,
                            background: form.scenario === sc.key ? `${sc.color}10` : 'transparent',
                            transition: 'all 0.15s',
                        }}>
                        <div style={{ fontWeight: 700, fontSize: 13, color: form.scenario === sc.key ? sc.color : 'var(--text-secondary)', marginBottom: 4 }}>
                            {sc.title}
                        </div>
                        <div style={{ fontSize: 10, color: 'var(--text-muted)', lineHeight: 1.4 }}>{sc.desc}</div>
                    </div>
                ))}
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
                {/* Formulario */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>

                    {/* Configuración básica */}
                    {!isRealistic && (
                        <>
                            <div>
                                <label style={labelStyle}>Endpoint objetivo</label>
                                <select value={form.endpoint} onChange={e => setField('endpoint', e.target.value)}
                                    disabled={isRunning} style={inputStyle}>
                                    {endpoints.map(ep => <option key={ep} value={ep}>{ep}</option>)}
                                </select>
                            </div>
                            <div>
                                <label style={labelStyle}>Método HTTP</label>
                                <select value={form.method} onChange={e => setField('method', e.target.value)}
                                    disabled={isRunning} style={inputStyle}>
                                    <option>GET</option><option>POST</option>
                                </select>
                            </div>
                        </>
                    )}

                    {/* Configuración realista */}
                    {isRealistic && (
                        <div style={{ background: 'rgba(99,102,241,0.08)', border: '1px solid rgba(99,102,241,0.2)', borderRadius: 8, padding: '10px 12px' }}>
                            <div style={{ fontSize: 11, fontWeight: 600, color: '#6366f1', marginBottom: 6 }}>Flujo simulado por usuario:</div>
                            {['GET /api/config → cargar configuración del tutor', 'POST /api/chat → pregunta aleatoria al asistente IA', '⏳ Think time → pausa realista entre mensajes', '↺ Repetir durante toda la prueba'].map((step, i) => (
                                <div key={i} style={{ fontSize: 10, color: 'var(--text-muted)', marginBottom: 3 }}>
                                    <span style={{ color: '#6366f1', marginRight: 6 }}>{i + 1}.</span>{step}
                                </div>
                            ))}
                            <div>
                                <label style={{ ...labelStyle, marginTop: 10 }}>
                                    Think time: <strong style={{ color: '#6366f1' }}>{form.think_time_ms}ms</strong>
                                </label>
                                <input type="range" min={0} max={5000} step={100} value={form.think_time_ms}
                                    onChange={e => setField('think_time_ms', +e.target.value)}
                                    disabled={isRunning} style={{ width: '100%' }} />
                                <div style={{ fontSize: 9, color: 'var(--text-muted)' }}>Pausa entre preguntas del mismo usuario</div>
                            </div>
                        </div>
                    )}

                    <div>
                        <label style={labelStyle}>
                            Usuarios concurrentes: <strong style={{ color: '#6366f1' }}>{form.concurrent_users}</strong>
                        </label>
                        <input type="range" min={1} max={isRealistic ? 50 : 200} value={form.concurrent_users}
                            onChange={e => setField('concurrent_users', +e.target.value)}
                            disabled={isRunning} style={{ width: '100%' }} />
                        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 9, color: 'var(--text-muted)' }}>
                            <span>1</span><span>{isRealistic ? '10' : '50'}</span><span>{isRealistic ? '25' : '100'}</span><span>{isRealistic ? '50' : '200'}</span>
                        </div>
                        {isRealistic && <div style={{ fontSize: 9, color: '#fbbf24' }}>⚠ Máx 50 en modo realista (la IA tiene latencia alta)</div>}
                    </div>

                    <div>
                        <label style={labelStyle}>
                            Duración: <strong style={{ color: '#6366f1' }}>{form.duration_seconds}s</strong>
                        </label>
                        <input type="range" min={5} max={120} step={5} value={form.duration_seconds}
                            onChange={e => setField('duration_seconds', +e.target.value)}
                            disabled={isRunning} style={{ width: '100%' }} />
                        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 9, color: 'var(--text-muted)' }}>
                            <span>5s</span><span>30s</span><span>60s</span><span>2m</span>
                        </div>
                    </div>

                    <div>
                        <label style={labelStyle}>
                            Ramp-up: <strong style={{ color: '#6366f1' }}>{form.ramp_up_seconds}s</strong>
                        </label>
                        <input type="range" min={0} max={30} value={form.ramp_up_seconds}
                            onChange={e => setField('ramp_up_seconds', +e.target.value)}
                            disabled={isRunning} style={{ width: '100%' }} />
                        <div style={{ fontSize: 9, color: 'var(--text-muted)' }}>
                            Escalar de 0 a {form.concurrent_users} usuarios gradualmente
                        </div>
                    </div>

                    {/* Preparar sesiones (solo modo realista) */}
                    {isRealistic && (
                        <div style={{ background: 'rgba(0,0,0,0.15)', borderRadius: 8, padding: '10px 12px' }}>
                            <div style={{ fontSize: 11, fontWeight: 600, marginBottom: 6, color: sessionsReady ? '#4ade80' : '#fbbf24' }}>
                                {sessionsReady ? `✅ ${state.sessions_ready} sesiones listas` : '⚠ Paso previo requerido'}
                            </div>
                            <div style={{ fontSize: 10, color: 'var(--text-muted)', marginBottom: 8, lineHeight: 1.4 }}>
                                Crea sesiones sintéticas de estudiantes en la BD para que el stress test pueda autenticarse y llamar a la IA.
                            </div>
                            <div style={{ display: 'flex', gap: 6 }}>
                                <button onClick={prepare} disabled={preparing || isRunning} style={{
                                    flex: 1, padding: '7px 0', borderRadius: 6, border: 'none', fontSize: 11,
                                    background: sessionsReady ? 'rgba(99,102,241,0.2)' : 'rgba(99,102,241,0.6)',
                                    color: 'white', cursor: preparing || isRunning ? 'default' : 'pointer', fontWeight: 600,
                                }}>
                                    {preparing ? '⏳ Preparando…' : sessionsReady ? '↺ Re-preparar sesiones' : '🔑 Preparar sesiones'}
                                </button>
                                {sessionsReady && (
                                    <button onClick={cleanup} disabled={isRunning} style={{
                                        padding: '7px 10px', borderRadius: 6, border: '1px solid rgba(239,68,68,0.4)',
                                        background: 'transparent', color: '#f87171', cursor: 'pointer', fontSize: 11,
                                    }}>🗑</button>
                                )}
                            </div>
                            {prepareMsg && (
                                <div style={{ fontSize: 10, marginTop: 6, color: prepareMsg.ok ? '#4ade80' : '#f87171' }}>
                                    {prepareMsg.text}
                                </div>
                            )}
                        </div>
                    )}

                    {/* Botones iniciar/detener */}
                    <div style={{ display: 'flex', gap: 8, marginTop: 4 }}>
                        {!isRunning ? (
                            <button onClick={start} disabled={!canStart} style={{
                                flex: 1, padding: '10px 0', borderRadius: 8, border: 'none',
                                background: canStart ? 'linear-gradient(135deg, #ef4444, #dc2626)' : 'rgba(255,255,255,0.05)',
                                color: canStart ? 'white' : 'var(--text-muted)',
                                fontWeight: 700, fontSize: 13,
                                cursor: canStart ? 'pointer' : 'not-allowed',
                            }}>
                                ▶ Iniciar prueba
                            </button>
                        ) : (
                            <button onClick={stop} style={{
                                flex: 1, padding: '10px 0', borderRadius: 8, border: 'none',
                                background: 'linear-gradient(135deg, #6b7280, #4b5563)',
                                color: 'white', fontWeight: 700, fontSize: 13, cursor: 'pointer',
                            }}>⏹ Detener</button>
                        )}
                    </div>
                </div>

                {/* Panel de resultados */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                    <div style={{ background: 'rgba(0,0,0,0.2)', borderRadius: 8, padding: 12 }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                            <span style={{ fontSize: 12, fontWeight: 600, color: isRunning ? '#fbbf24' : isDone ? '#4ade80' : 'var(--text-muted)' }}>
                                {isRunning ? '⚡ Ejecutando…' : isDone ? '✅ Completado' : '○ En espera'}
                            </span>
                            {isRunning && (
                                <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                                    {state.active_users} usuarios activos
                                </span>
                            )}
                        </div>
                        <div style={{ height: 6, background: 'rgba(255,255,255,0.08)', borderRadius: 3, overflow: 'hidden' }}>
                            <div style={{
                                height: '100%', borderRadius: 3, width: `${pct}%`,
                                background: isRunning ? 'linear-gradient(90deg, #6366f1, #ef4444)' : '#4ade80',
                                transition: 'width 0.5s ease',
                            }} />
                        </div>
                        <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 4, textAlign: 'right' }}>{pct}%</div>

                        {/* Pregunta actual (modo realista) */}
                        {isRunning && isRealistic && state.current_question && (
                            <div style={{ marginTop: 8, padding: '6px 8px', background: 'rgba(99,102,241,0.1)', borderRadius: 6, fontSize: 10, color: '#a78bfa', fontStyle: 'italic' }}>
                                💬 "{state.current_question}"
                            </div>
                        )}
                    </div>

                    {(isRunning || isDone) && s.total > 0 && (
                        <>
                            {/* Resultados de red / latencia */}
                            <div style={{ fontSize: 10, fontWeight: 600, color: 'var(--text-muted)', marginBottom: 4, letterSpacing: 1 }}>
                                RED &amp; LATENCIA
                            </div>
                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6, marginBottom: 10 }}>
                                {[
                                    { l: 'Total req', v: s.total, c: '#6366f1' },
                                    { l: 'RPS', v: s.rps, c: '#4ade80' },
                                    { l: 'Latencia prom', v: `${s.avg_ms} ms`, c: '#fbbf24' },
                                    { l: 'P50', v: `${s.p50_ms} ms`, c: '#fbbf24' },
                                    { l: 'P95', v: `${s.p95_ms} ms`, c: '#f59e0b' },
                                    { l: 'P99', v: `${s.p99_ms} ms`, c: '#f87171' },
                                    { l: 'Mín / Máx', v: `${s.min_ms} / ${s.max_ms} ms`, c: 'var(--text-secondary)' },
                                    { l: 'Exitosos', v: s.success, c: '#4ade80' },
                                    { l: 'Errores', v: `${s.failed} (${s.error_rate}%)`, c: s.failed > 0 ? '#f87171' : '#4ade80' },
                                    { l: 'Duración', v: `${s.elapsed_s}s`, c: 'var(--text-secondary)' },
                                ].map(({ l, v, c }) => (
                                    <div key={l} style={{ background: 'rgba(0,0,0,0.2)', borderRadius: 6, padding: '8px 10px' }}>
                                        <div style={{ fontSize: 9, color: 'var(--text-muted)' }}>{l}</div>
                                        <div style={{ fontSize: 14, fontWeight: 700, color: c }}>{v}</div>
                                    </div>
                                ))}
                            </div>

                            {/* Recursos del servidor durante la prueba */}
                            {s.resources && s.resources.peak_cpu_pct !== undefined && (
                                <>
                                    <div style={{ fontSize: 10, fontWeight: 600, color: 'var(--text-muted)', marginBottom: 4, letterSpacing: 1 }}>
                                        RECURSOS DEL SERVIDOR
                                    </div>
                                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6, marginBottom: 10 }}>
                                        {[
                                            { l: 'CPU prom', v: `${s.resources.avg_cpu_pct}%`, c: '#4ade80' },
                                            { l: 'CPU pico', v: `${s.resources.peak_cpu_pct}%`, c: s.resources.peak_cpu_pct > 80 ? '#f87171' : '#fbbf24' },
                                            { l: 'RAM prom', v: `${s.resources.avg_ram_mb} MB`, c: '#4ade80' },
                                            { l: 'RAM pico', v: `${s.resources.peak_ram_mb} MB (${s.resources.peak_ram_pct}%)`, c: s.resources.peak_ram_pct > 80 ? '#f87171' : '#fbbf24' },
                                            { l: 'Usuarios pico', v: s.resources.peak_concurrent_users, c: '#6366f1' },
                                            { l: 'Usuarios prom', v: s.resources.avg_concurrent_users, c: '#a78bfa' },
                                        ].map(({ l, v, c }) => (
                                            <div key={l} style={{ background: 'rgba(0,0,0,0.2)', borderRadius: 6, padding: '8px 10px' }}>
                                                <div style={{ fontSize: 9, color: 'var(--text-muted)' }}>{l}</div>
                                                <div style={{ fontSize: 13, fontWeight: 700, color: c }}>{v}</div>
                                            </div>
                                        ))}
                                    </div>

                                    {/* Coste por sesión */}
                                    <div style={{ fontSize: 10, fontWeight: 600, color: 'var(--text-muted)', marginBottom: 4, letterSpacing: 1 }}>
                                        COSTE ESTIMADO POR SESIÓN (en pico)
                                    </div>
                                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6, marginBottom: 10 }}>
                                        <div style={{ background: 'rgba(99,102,241,0.12)', border: '1px solid rgba(99,102,241,0.3)', borderRadius: 6, padding: '10px 12px' }}>
                                            <div style={{ fontSize: 9, color: 'var(--text-muted)' }}>CPU / sesión</div>
                                            <div style={{ fontSize: 18, fontWeight: 700, color: '#6366f1' }}>{s.resources.per_session_cpu_pct}%</div>
                                            <div style={{ fontSize: 8, color: 'var(--text-muted)', marginTop: 2 }}>del total del sistema</div>
                                        </div>
                                        <div style={{ background: 'rgba(251,191,36,0.12)', border: '1px solid rgba(251,191,36,0.3)', borderRadius: 6, padding: '10px 12px' }}>
                                            <div style={{ fontSize: 9, color: 'var(--text-muted)' }}>RAM / sesión</div>
                                            <div style={{ fontSize: 18, fontWeight: 700, color: '#fbbf24' }}>{s.resources.per_session_ram_mb} MB</div>
                                            <div style={{ fontSize: 8, color: 'var(--text-muted)', marginTop: 2 }}>memoria estimada</div>
                                        </div>
                                    </div>

                                    {/* Mini-timeline CPU/RAM */}
                                    {isDone && s.resources.timeline && s.resources.timeline.length > 0 && (
                                        <div style={{ background: 'rgba(0,0,0,0.2)', borderRadius: 8, padding: 10 }}>
                                            <div style={{ fontSize: 9, color: 'var(--text-muted)', marginBottom: 6, fontWeight: 600 }}>
                                                EVOLUCIÓN DURANTE LA PRUEBA
                                            </div>
                                            <ResponsiveContainer width="100%" height={80}>
                                                <LineChart data={s.resources.timeline} margin={{ top: 0, right: 0, left: -30, bottom: 0 }}>
                                                    <CartesianGrid strokeDasharray="2 2" stroke="rgba(255,255,255,0.05)" />
                                                    <XAxis dataKey="t" tick={{ fontSize: 8, fill: 'rgba(255,255,255,0.3)' }} tickFormatter={v => `${v}s`} />
                                                    <YAxis tick={{ fontSize: 8, fill: 'rgba(255,255,255,0.3)' }} />
                                                    <Tooltip
                                                        contentStyle={{ background: '#1a1a2e', border: '1px solid rgba(255,255,255,0.1)', fontSize: 10 }}
                                                        formatter={(v, name) => [name === 'cpu' ? `${v}%` : `${v} MB`, name === 'cpu' ? 'CPU' : 'RAM']}
                                                        labelFormatter={v => `t=${v}s`}
                                                    />
                                                    <Line type="monotone" dataKey="cpu" stroke="#6366f1" dot={false} strokeWidth={1.5} name="cpu" />
                                                    <Line type="monotone" dataKey="ram_mb" stroke="#fbbf24" dot={false} strokeWidth={1.5} name="ram_mb" />
                                                </LineChart>
                                            </ResponsiveContainer>
                                            <div style={{ display: 'flex', gap: 12, marginTop: 4, fontSize: 9, color: 'var(--text-muted)' }}>
                                                <span><span style={{ color: '#6366f1' }}>●</span> CPU %</span>
                                                <span><span style={{ color: '#fbbf24' }}>●</span> RAM MB</span>
                                            </div>
                                        </div>
                                    )}
                                </>
                            )}
                        </>
                    )}

                    {/* Pool de preguntas (modo realista, en espera) */}
                    {isRealistic && state.status === 'idle' && questions.length > 0 && (
                        <div style={{ background: 'rgba(0,0,0,0.15)', borderRadius: 8, padding: 10 }}>
                            <div style={{ fontSize: 10, fontWeight: 600, color: 'var(--text-muted)', marginBottom: 6 }}>
                                Pool de preguntas ({questions.length}):
                            </div>
                            <div style={{ maxHeight: 120, overflowY: 'auto' }}>
                                {questions.map((q, i) => (
                                    <div key={i} style={{ fontSize: 9, color: 'rgba(255,255,255,0.4)', marginBottom: 3, padding: '2px 0', borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                                        {i + 1}. {q}
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    {state.status === 'idle' && !isRealistic && (
                        <div style={{ fontSize: 11, color: 'var(--text-muted)', textAlign: 'center', padding: 20 }}>
                            Configura los parámetros e inicia la prueba.<br />
                            Los resultados aparecen en tiempo real.
                        </div>
                    )}
                </div>
            </div>
        </div>
    )
}


// ══════════════════════════════════════════════════════════════════════════════
// Sección de Métricas por Sesión
// ══════════════════════════════════════════════════════════════════════════════
function SessionsPanel({ sessions }) {
    if (!sessions) return null
    const { total_sessions, active_sessions_5min, avg_requests_per_session,
        avg_latency_per_session_ms, avg_duration_per_session_s,
        per_session_resources, sessions: list } = sessions

    const psr = per_session_resources || {}

    return (
        <div className="section-card">
            <div className="section-card__title" style={{ marginBottom: 14 }}>
                👤 Recursos por Sesión de Usuario
                <span style={{ fontSize: 11, fontWeight: 400, color: 'var(--text-muted)', marginLeft: 8 }}>
                    Estimación basada en sesiones activas (últimos 5 min)
                </span>
            </div>

            {/* KPIs de sesión */}
            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginBottom: 16 }}>
                <KpiCard label="Sesiones totales" value={total_sessions} icon="🔑" color="#6366f1" />
                <KpiCard label="Activas (5 min)" value={active_sessions_5min} icon="🟢" color="#4ade80" />
                <KpiCard label="Req/sesión prom" value={avg_requests_per_session} icon="📊" color="#fbbf24" />
                <KpiCard label="Latencia/sesión" value={avg_latency_per_session_ms} unit="ms" icon="⏱" color="#f59e0b" />
                <KpiCard label="Duración/sesión" value={avg_duration_per_session_s} unit="s" icon="⏳" color="#a78bfa" />
            </div>

            {/* Recursos por sesión estimados */}
            <div style={{ background: 'rgba(99,102,241,0.06)', border: '1px solid rgba(99,102,241,0.2)', borderRadius: 8, padding: '12px 16px', marginBottom: 14 }}>
                <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 10, color: 'var(--accent-primary)' }}>
                    Estimación de recursos por sesión activa
                </div>
                <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
                    {[
                        { label: 'CPU por sesión', value: `${psr.cpu_pct ?? 0}%`, icon: '🖥️',
                          hint: `${active_sessions_5min} sesión${active_sessions_5min !== 1 ? 'es' : ''} activa${active_sessions_5min !== 1 ? 's' : ''}` },
                        { label: 'RAM por sesión', value: `${psr.ram_mb ?? 0} MB`, icon: '💾',
                          hint: 'RAM usada / sesiones activas' },
                        { label: 'Disco por sesión', value: `${psr.disk_mb ? (psr.disk_mb / 1024).toFixed(1) : 0} GB`, icon: '💿',
                          hint: 'Disco usado / sesiones activas' },
                    ].map(({ label, value, icon, hint }) => (
                        <div key={label} style={{ flex: 1, minWidth: 140, background: 'var(--bg-elevated)', borderRadius: 8, padding: '10px 14px', border: '1px solid var(--border)' }}>
                            <div style={{ fontSize: 18, marginBottom: 4 }}>{icon}</div>
                            <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>{label}</div>
                            <div style={{ fontSize: 22, fontWeight: 700, color: '#6366f1' }}>{value}</div>
                            <div style={{ fontSize: 9, color: 'var(--text-muted)', marginTop: 2 }}>{hint}</div>
                        </div>
                    ))}
                </div>
                <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 10 }}>
                    * Estimación: recursos totales del servidor divididos entre sesiones activas. Los valores individuales varían según la actividad de cada usuario.
                </div>
            </div>

            {/* Tabla de sesiones */}
            {list && list.length > 0 && (
                <>
                    <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 8, color: 'var(--text-secondary)' }}>
                        Sesiones recientes
                    </div>
                    <div style={{ overflowX: 'auto' }}>
                        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11 }}>
                            <thead>
                                <tr style={{ borderBottom: '1px solid var(--border)' }}>
                                    {['Session ID', 'Requests', 'Lat. prom', 'Errores', 'Duración', 'Último acceso'].map(h => (
                                        <th key={h} style={{ padding: '6px 10px', textAlign: 'left', color: 'var(--text-muted)', fontWeight: 600 }}>{h}</th>
                                    ))}
                                </tr>
                            </thead>
                            <tbody>
                                {list.map((s, i) => (
                                    <tr key={i} style={{ borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                                        <td style={{ padding: '6px 10px', fontFamily: 'monospace', color: '#a78bfa' }}>{s.id}</td>
                                        <td style={{ padding: '6px 10px', color: 'var(--text-secondary)' }}>{s.requests}</td>
                                        <td style={{ padding: '6px 10px', color: latColor(s.avg_latency_ms) }}>{s.avg_latency_ms} ms</td>
                                        <td style={{ padding: '6px 10px', color: s.errors > 0 ? '#f87171' : '#4ade80' }}>{s.errors}</td>
                                        <td style={{ padding: '6px 10px', color: 'var(--text-muted)' }}>{s.duration_s}s</td>
                                        <td style={{ padding: '6px 10px', color: 'var(--text-muted)' }}>
                                            {s.last_seen_ago_s < 60 ? `hace ${s.last_seen_ago_s}s` : `hace ${Math.round(s.last_seen_ago_s / 60)}min`}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </>
            )}

            {(!list || list.length === 0) && (
                <div style={{ fontSize: 12, color: 'var(--text-muted)', textAlign: 'center', padding: 16 }}>
                    Sin sesiones registradas aún. Las sesiones aparecen cuando usuarios acceden via LTI.
                </div>
            )}
        </div>
    )
}


// ══════════════════════════════════════════════════════════════════════════════
// Historial persistido de pruebas de estrés
// ══════════════════════════════════════════════════════════════════════════════
function StressHistoryPanel() {
    const [history, setHistory] = useState([])
    const [loading, setLoading] = useState(true)

    useEffect(() => {
        api.get('/api/metrics/stress-test/history')
            .then(r => setHistory(r.data))
            .catch(() => {})
            .finally(() => setLoading(false))
    }, [])

    const fmtDate = ts => new Date(ts * 1000).toLocaleString('es-ES', { dateStyle: 'short', timeStyle: 'short' })
    const scenarioBadge = s => s === 'realistic'
        ? <span style={{ background: 'rgba(99,102,241,0.2)', color: '#a78bfa', borderRadius: 4, padding: '1px 6px', fontSize: 9 }}>🎓 Realista</span>
        : <span style={{ background: 'rgba(74,222,128,0.15)', color: '#4ade80', borderRadius: 4, padding: '1px 6px', fontSize: 9 }}>⚡ Básico</span>

    return (
        <div className="section-card">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
                <div className="section-card__title" style={{ margin: 0 }}>
                    📋 Historial de Pruebas de Estrés
                    <span style={{ fontSize: 11, fontWeight: 400, color: 'var(--text-muted)', marginLeft: 8 }}>
                        Guardado automáticamente en <code style={{ fontSize: 10 }}>data/stress_results.jsonl</code>
                    </span>
                </div>
                <a href="/api/metrics/export/stress-results" download
                    style={{ padding: '5px 12px', fontSize: 11, borderRadius: 6, border: '1px solid rgba(99,102,241,0.4)', background: 'rgba(99,102,241,0.1)', color: '#a78bfa', textDecoration: 'none', whiteSpace: 'nowrap' }}>
                    ⬇ Exportar CSV
                </a>
            </div>

            {loading && <div style={{ color: 'var(--text-muted)', fontSize: 12, textAlign: 'center', padding: 12 }}>Cargando historial…</div>}
            {!loading && history.length === 0 && (
                <div style={{ color: 'var(--text-muted)', fontSize: 12, textAlign: 'center', padding: 16 }}>
                    Sin pruebas registradas aún. Los resultados se guardan automáticamente al finalizar cada prueba.
                </div>
            )}
            {!loading && history.length > 0 && (
                <div style={{ overflowX: 'auto' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11 }}>
                        <thead>
                            <tr style={{ borderBottom: '1px solid var(--border)' }}>
                                {['Fecha', 'Escenario', 'Usuarios', 'Duración', 'Total req', 'RPS', 'Error %', 'Lat. prom', 'P95', 'CPU pico', 'RAM pico', 'CPU/sesión', 'RAM/sesión'].map(h => (
                                    <th key={h} style={{ padding: '6px 8px', textAlign: 'left', color: 'var(--text-muted)', fontWeight: 600, whiteSpace: 'nowrap' }}>{h}</th>
                                ))}
                            </tr>
                        </thead>
                        <tbody>
                            {history.map((r, i) => {
                                const res = r.results || {}
                                const cfg = r.config || {}
                                const rsc = r.resources || {}
                                const errColor = (res.error_rate || 0) > 20 ? '#f87171' : (res.error_rate || 0) > 5 ? '#fbbf24' : '#4ade80'
                                return (
                                    <tr key={i} style={{ borderBottom: '1px solid rgba(255,255,255,0.04)', background: i === 0 ? 'rgba(99,102,241,0.04)' : 'transparent' }}>
                                        <td style={{ padding: '7px 8px', color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>{fmtDate(r.timestamp)}</td>
                                        <td style={{ padding: '7px 8px' }}>{scenarioBadge(cfg.scenario)}</td>
                                        <td style={{ padding: '7px 8px', color: '#6366f1', fontWeight: 600 }}>{cfg.concurrent_users}</td>
                                        <td style={{ padding: '7px 8px', color: 'var(--text-muted)' }}>{res.elapsed_s}s</td>
                                        <td style={{ padding: '7px 8px', color: 'var(--text-secondary)' }}>{res.total}</td>
                                        <td style={{ padding: '7px 8px', color: '#4ade80', fontWeight: 600 }}>{res.rps}</td>
                                        <td style={{ padding: '7px 8px', color: errColor, fontWeight: 600 }}>{res.error_rate}%</td>
                                        <td style={{ padding: '7px 8px', color: '#fbbf24' }}>{res.avg_ms} ms</td>
                                        <td style={{ padding: '7px 8px', color: '#f59e0b' }}>{res.p95_ms} ms</td>
                                        <td style={{ padding: '7px 8px', color: rsc.peak_cpu_pct > 80 ? '#f87171' : '#4ade80' }}>{rsc.peak_cpu_pct ?? '—'}%</td>
                                        <td style={{ padding: '7px 8px', color: '#a78bfa' }}>{rsc.peak_ram_mb ?? '—'} MB</td>
                                        <td style={{ padding: '7px 8px', color: '#6366f1' }}>{rsc.per_session_cpu_pct ?? '—'}%</td>
                                        <td style={{ padding: '7px 8px', color: '#fbbf24' }}>{rsc.per_session_ram_mb ?? '—'} MB</td>
                                    </tr>
                                )
                            })}
                        </tbody>
                    </table>
                </div>
            )}
        </div>
    )
}


// ══════════════════════════════════════════════════════════════════════════════
// Dashboard principal
// ══════════════════════════════════════════════════════════════════════════════
export default function MetricsDashboard() {
    const [data, setData] = useState(null)
    const [recent, setRecent] = useState([])
    const [loading, setLoading] = useState(true)
    const [lastUpdate, setLastUpdate] = useState(null)
    const [autoRefresh, setAutoRefresh] = useState(true)

    const fetchData = useCallback(async () => {
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

    useEffect(() => { fetchData() }, [fetchData])
    useEffect(() => {
        if (!autoRefresh) return
        const id = setInterval(fetchData, 5000)
        return () => clearInterval(id)
    }, [autoRefresh, fetchData])

    if (loading) return <div style={{ padding: 60, textAlign: 'center', color: C.muted, fontSize: 14 }}>Cargando métricas…</div>
    if (!data) return <div style={{ padding: 60, textAlign: 'center', color: C.red }}>No se pudieron obtener las métricas.</div>

    const { system, summary_60s: s60, summary_300s: s300, endpoints, timeline, sessions,
            resource_history: resHistory = [], resource_peaks: resPeaks = {} } = data

    const timelineData = (timeline || []).map((t, i) => ({
        name: i % 5 === 0 ? `${Math.round((timeline.length - i) * (300 / timeline.length))}s` : '',
        'Req': t.count,
        'Lat ms': t.avg_ms,
    }))

    const sectionTitle = (txt, sub) => (
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginBottom: 16, paddingBottom: 10, borderBottom: `1px solid ${C.border}` }}>
            <span style={{ fontSize: 13, fontWeight: 700, color: 'rgba(255,255,255,0.9)', textTransform: 'uppercase', letterSpacing: 0.6 }}>{txt}</span>
            {sub && <span style={{ fontSize: 11, color: C.muted, fontWeight: 400 }}>{sub}</span>}
        </div>
    )

    return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 18, maxWidth: 1400, margin: '0 auto' }}>

            {/* Header */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                    <div style={{ fontSize: 20, fontWeight: 800, color: 'white', letterSpacing: -0.5 }}>Métricas del Sistema</div>
                    {lastUpdate && <div style={{ fontSize: 11, color: C.muted, marginTop: 2 }}>Actualizado: {lastUpdate.toLocaleTimeString()}</div>}
                </div>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                    <label style={{ fontSize: 11, color: C.muted, display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}>
                        <input type="checkbox" checked={autoRefresh} onChange={e => setAutoRefresh(e.target.checked)} />
                        Auto-refresh 5s
                    </label>
                    <a href="/api/metrics/export/resource-history" download
                        style={{ padding: '6px 12px', fontSize: 11, borderRadius: 6, border: `1px solid ${C.greenDim.replace('0.15', '0.4')}`, background: C.greenDim, color: C.green, textDecoration: 'none', fontWeight: 600 }}>
                        ⬇ Recursos CSV
                    </a>
                    <button onClick={fetchData} style={{ padding: '6px 14px', fontSize: 11, borderRadius: 6, border: `1px solid ${C.border}`, background: C.card, color: 'rgba(255,255,255,0.7)', cursor: 'pointer', fontWeight: 600 }}>↻ Actualizar</button>
                </div>
            </div>

            {/* KPIs de requests — 2 filas, grid completo */}
            <div className="section-card">
                {sectionTitle('Requests', 'último minuto')}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)', gap: 10 }}>
                    <KpiCard label="Total requests" value={s60.total} icon="📊" color={C.indigo} />
                    <KpiCard label="Req/segundo" value={s60.rps} icon="⚡" color={C.green} />
                    <KpiCard label="Latencia prom" value={s60.avg_ms} unit="ms" icon="⏱" color={C.amber} />
                    <KpiCard label="Latencia p95" value={s60.p95_ms} unit="ms" icon="📈" color={C.orange} />
                    <KpiCard label="Latencia p99" value={s60.p99_ms} unit="ms" icon="🎯" color={C.red} sub="peor 1% de req" />
                    <KpiCard label="Tasa de error" value={s60.error_rate} unit="%" icon="❌" color={s60.error_rate > 5 ? C.red : C.green} sub={`${s60.errors} errores`} />
                </div>
            </div>

            {/* Gauges + Picos + Historial en una sola card */}
            <div className="section-card">
                {sectionTitle('Recursos del servidor', 'tiempo real')}

                {/* Gauges */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16, marginBottom: 24 }}>
                    <Gauge value={system.cpu.percent} label={`CPU · ${system.cpu.count} núcleos`} />
                    <Gauge value={system.ram.percent} label={`RAM · ${system.ram.used_mb} / ${system.ram.total_mb} MB`} />
                    <Gauge value={system.disk.percent} label={`Disco · ${system.disk.used_gb} / ${system.disk.total_gb} GB`} color={C.violet} />
                    <Gauge value={system.network.active_connections} max={100} unit="conn" label="Conexiones activas" color={C.blue} />
                </div>

                {/* Info pills */}
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 20 }}>
                    {[
                        ['RAM libre', `${system.ram.available_mb} MB`],
                        ['Disco libre', `${system.disk.free_gb} GB`],
                        ['Req 5 min', s300.total],
                        ['RPS 5 min', s300.rps],
                    ].map(([l, v]) => (
                        <div key={l} style={statPill}>{l}: <b style={{ color: 'white' }}>{v}</b></div>
                    ))}
                </div>

                {/* Picos — últimos 5 minutos */}
                {resPeaks.cpu && (
                    <>
                        <div style={{ fontSize: 10, fontWeight: 700, color: C.muted, margin: '4px 0 10px', letterSpacing: 1 }}>
                            PICOS — ÚLTIMOS 5 MIN ({resPeaks.samples} muestras)
                        </div>
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 10, marginBottom: 20 }}>
                            {[
                                { l: 'CPU pico', v: `${resPeaks.cpu.peak}%`, s: `prom ${resPeaks.cpu.avg}%  ·  mín ${resPeaks.cpu.min}%`, c: resPeaks.cpu.peak > 80 ? C.red : resPeaks.cpu.peak > 50 ? C.amber : C.green },
                                { l: 'RAM pico', v: `${resPeaks.ram_pct.peak}%`, s: `${resPeaks.ram_mb.peak} MB  ·  prom ${resPeaks.ram_pct.avg}%`, c: resPeaks.ram_pct.peak > 85 ? C.red : resPeaks.ram_pct.peak > 65 ? C.amber : C.green },
                                { l: 'RAM pico (MB)', v: `${resPeaks.ram_mb.peak} MB`, s: `prom ${resPeaks.ram_mb.avg} MB  ·  mín ${resPeaks.ram_mb.min}`, c: C.violet },
                                { l: 'Disco pico', v: `${resPeaks.disk_pct.peak}%`, s: `prom ${resPeaks.disk_pct.avg}%`, c: resPeaks.disk_pct.peak > 90 ? C.red : C.blue },
                            ].map(({ l, v, s, c }) => (
                                <div key={l} style={{ background: 'rgba(0,0,0,0.3)', borderRadius: 10, padding: '12px 14px', borderLeft: `3px solid ${c}` }}>
                                    <div style={{ fontSize: 10, color: C.muted, marginBottom: 4, fontWeight: 600 }}>{l}</div>
                                    <div style={{ fontSize: 22, fontWeight: 800, color: c, lineHeight: 1 }}>{v}</div>
                                    <div style={{ fontSize: 10, color: C.dim, marginTop: 5 }}>{s}</div>
                                </div>
                            ))}
                        </div>
                    </>
                )}

                {/* Historial de recursos — gráfica */}
                {resHistory.length > 0 && (
                    <>
                        <div style={{ fontSize: 10, fontWeight: 700, color: C.muted, margin: '4px 0 10px', letterSpacing: 1 }}>
                            EVOLUCIÓN DE RECURSOS (últimos 5 min)
                        </div>
                        <ResponsiveContainer width="100%" height={180}>
                            <LineChart
                                data={resHistory.map((s, i) => ({
                                    name: i % Math.max(1, Math.floor(resHistory.length / 8)) === 0
                                        ? `${Math.round((resHistory.length - i) * 5 / 60)}min`
                                        : '',
                                    cpu: s.cpu,
                                    ram_pct: s.ram_pct,
                                    disk_pct: s.disk_pct,
                                }))}
                                margin={{ top: 4, right: 10, left: -10, bottom: 0 }}
                            >
                                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                                <XAxis dataKey="name" tick={{ fill: C.muted, fontSize: 10 }} />
                                <YAxis domain={[0, 100]} unit="%" tick={{ fill: 'rgba(255,255,255,0.3)', fontSize: 9 }} />
                                <Tooltip
                                    contentStyle={{ background: '#1a1a2e', border: '1px solid rgba(255,255,255,0.1)', fontSize: 10 }}
                                    formatter={(v, name) => [`${v}%`, name === 'cpu' ? 'CPU' : name === 'ram_pct' ? 'RAM' : 'Disco']}
                                />
                                <Line type="monotone" dataKey="cpu" stroke="#6366f1" dot={false} strokeWidth={2} name="cpu" />
                                <Line type="monotone" dataKey="ram_pct" stroke="#fbbf24" dot={false} strokeWidth={2} name="ram_pct" />
                                <Line type="monotone" dataKey="disk_pct" stroke="#a78bfa" dot={false} strokeWidth={1.5} name="disk_pct" strokeDasharray="4 2" />
                            </LineChart>
                        </ResponsiveContainer>
                        <div style={{ display: 'flex', gap: 14, marginTop: 6, fontSize: 10, color: C.muted }}>
                            <span><span style={{ color: C.indigo }}>●</span> CPU %</span>
                            <span><span style={{ color: C.amber }}>●</span> RAM %</span>
                            <span><span style={{ color: C.violet }}>- -</span> Disco %</span>
                        </div>
                    </>
                )}
                {resHistory.length === 0 && (
                    <div style={{ fontSize: 11, color: C.muted, marginTop: 12, textAlign: 'center' }}>
                        El historial se acumula cada 5 s — espera unos segundos…
                    </div>
                )}
            </div>

            {/* Actividad + Endpoints en grid de 2 columnas */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 18 }}>
                {/* Timeline */}
                <div className="section-card">
                    {sectionTitle('Actividad', 'últimos 5 minutos')}
                    <ResponsiveContainer width="100%" height={200}>
                        <LineChart data={timelineData} margin={{ top: 4, right: 10, left: -10, bottom: 0 }}>
                            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                            <XAxis dataKey="name" tick={{ fill: C.muted, fontSize: 9 }} />
                            <YAxis yAxisId="req" tick={{ fill: C.muted, fontSize: 9 }} />
                            <YAxis yAxisId="lat" orientation="right" tick={{ fill: C.muted, fontSize: 9 }} />
                            <Tooltip content={<CustomTooltip />} />
                            <Legend wrapperStyle={{ fontSize: 11, paddingTop: 8, color: 'rgba(255,255,255,0.6)' }} />
                            <Line yAxisId="req" type="monotone" dataKey="Req" stroke={C.indigo} strokeWidth={2.5} dot={false} />
                            <Line yAxisId="lat" type="monotone" dataKey="Lat ms" stroke={C.amber} strokeWidth={2.5} dot={false} />
                        </LineChart>
                    </ResponsiveContainer>
                </div>

                {/* Latencia por endpoint */}
                {endpoints && endpoints.length > 0 && (
                    <div className="section-card">
                        {sectionTitle('Latencia por endpoint', 'últimos 5 min')}
                        <ResponsiveContainer width="100%" height={Math.max(160, Math.min(endpoints.length, 8) * 32)}>
                            <BarChart data={endpoints.slice(0, 8)} layout="vertical" margin={{ top: 0, right: 50, left: 0, bottom: 0 }}>
                                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" horizontal={false} />
                                <XAxis type="number" tick={{ fill: C.muted, fontSize: 9 }} unit="ms" />
                                <YAxis type="category" dataKey="endpoint" width={130} tick={{ fill: 'rgba(255,255,255,0.6)', fontSize: 9 }} />
                                <Tooltip content={<CustomTooltip />} />
                                <Bar dataKey="avg_ms" name="Prom ms" fill={C.indigo} radius={[0, 4, 4, 0]} />
                                <Bar dataKey="p95_ms" name="P95 ms" fill={C.orange} radius={[0, 4, 4, 0]} />
                            </BarChart>
                        </ResponsiveContainer>
                    </div>
                )}
            </div>

            {/* Tabla endpoints + requests recientes en grid */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 18 }}>
                {endpoints && endpoints.length > 0 && (
                    <div className="section-card">
                        {sectionTitle('Endpoints', 'detalle')}
                        <div style={{ overflowX: 'auto' }}>
                            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11 }}>
                                <thead>
                                    <tr style={{ borderBottom: `1px solid ${C.border}` }}>
                                        {['Endpoint', 'Req', 'Prom', 'P95', 'Err'].map(h => (
                                            <th key={h} style={{ padding: '7px 8px', textAlign: 'left', color: C.muted, fontWeight: 700 }}>{h}</th>
                                        ))}
                                    </tr>
                                </thead>
                                <tbody>
                                    {endpoints.map((ep, i) => (
                                        <tr key={i} style={{ borderBottom: `1px solid ${C.border}` }}>
                                            <td style={{ padding: '7px 8px', fontFamily: 'monospace', color: C.violet, fontSize: 10 }}>{ep.endpoint}</td>
                                            <td style={{ padding: '7px 8px', color: 'rgba(255,255,255,0.7)', fontWeight: 600 }}>{ep.count}</td>
                                            <td style={{ padding: '7px 8px', color: latColor(ep.avg_ms), fontWeight: 600 }}>{ep.avg_ms} ms</td>
                                            <td style={{ padding: '7px 8px', color: latColor(ep.p95_ms) }}>{ep.p95_ms} ms</td>
                                            <td style={{ padding: '7px 8px', color: ep.errors > 0 ? C.red : C.muted }}>{ep.errors}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </div>
                )}

                {/* Últimos requests */}
                {recent.length > 0 && (
                    <div className="section-card">
                        {sectionTitle('Últimos requests', '2 minutos')}
                        <div style={{ overflowX: 'auto' }}>
                            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11 }}>
                                <thead>
                                    <tr style={{ borderBottom: `1px solid ${C.border}` }}>
                                        {['Hora', 'Método', 'Ruta', 'Estado', 'ms', 'Tipo'].map(h => (
                                            <th key={h} style={{ padding: '7px 8px', textAlign: 'left', color: C.muted, fontWeight: 700 }}>{h}</th>
                                        ))}
                                    </tr>
                                </thead>
                                <tbody>
                                    {recent.map((r, i) => (
                                        <tr key={i} style={{ borderBottom: `1px solid ${C.border}`, opacity: r.is_stress ? 0.65 : 1 }}>
                                            <td style={{ padding: '6px 8px', color: C.muted, fontSize: 10 }}>{new Date(r.timestamp * 1000).toLocaleTimeString()}</td>
                                            <td style={{ padding: '6px 8px', color: C.blue, fontWeight: 700, fontSize: 10 }}>{r.method}</td>
                                            <td style={{ padding: '6px 8px', fontFamily: 'monospace', color: 'rgba(255,255,255,0.65)', fontSize: 10, maxWidth: 160, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.path}</td>
                                            <td style={{ padding: '6px 8px' }}><StatusBadge code={r.status_code} /></td>
                                            <td style={{ padding: '6px 8px', color: latColor(r.duration_ms), fontWeight: 600 }}>{r.duration_ms}</td>
                                            <td style={{ padding: '6px 8px' }}>
                                                {r.is_stress
                                                    ? <span style={{ fontSize: 9, color: C.red, background: C.redDim, padding: '2px 6px', borderRadius: 4, fontWeight: 600 }}>🔥 stress</span>
                                                    : <span style={{ fontSize: 9, color: C.green, background: C.greenDim, padding: '2px 6px', borderRadius: 4, fontWeight: 600 }}>real</span>
                                                }
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                        </table>
                    </div>
                </div>
            )}
            </div>

            {/* Sección de sesiones */}
            <SessionsPanel sessions={sessions} />

            {/* Historial de pruebas */}
            <StressHistoryPanel />

            {/* Stress Test */}
            <StressTestPanel />
        </div>
    )
}

// ── Estilos ──────────────────────────────────────────────────────────────────
const labelStyle = { fontSize: 11, color: 'var(--text-muted)', display: 'block', marginBottom: 4 }
const inputStyle = {
    width: '100%', padding: '7px 10px', borderRadius: 6, fontSize: 12,
    background: 'var(--bg-elevated)', border: '1px solid var(--border)',
    color: 'var(--text-primary)', outline: 'none',
}
