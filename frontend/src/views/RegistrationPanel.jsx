import { useState, useEffect } from 'react'
import axios from 'axios'

const api = axios.create({ baseURL: '', withCredentials: true })

function CopyBtn({ value }) {
    const [done, setDone] = useState(false)
    const copy = () => {
        navigator.clipboard.writeText(value)
        setDone(true)
        setTimeout(() => setDone(false), 1500)
    }
    return (
        <button className="icon-btn" style={{ padding: '2px 8px', fontSize: '10px' }} onClick={copy}>
            {done ? '✓ Copiado' : '📋 Copiar'}
        </button>
    )
}

function FieldRow({ label, value, hint }) {
    return (
        <div className="info-row" style={{ marginBottom: 10 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8 }}>
                <div>
                    <span className="info-row__label">{label}</span>
                    {hint && <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 2 }}>{hint}</div>}
                </div>
                <CopyBtn value={value} />
            </div>
            <code style={{ display: 'block', marginTop: 4, fontSize: '11px', color: 'var(--text-primary)', fontFamily: 'monospace', wordBreak: 'break-all', background: 'rgba(0,0,0,0.2)', padding: '4px 8px', borderRadius: 4 }}>
                {value}
            </code>
        </div>
    )
}

const EMPTY_MANUAL = {
    label: '', issuer: 'http://local.openedx.io', client_id: '',
    deployment_id: '1', keyset_url: '', auth_endpoint: '', token_endpoint: '',
}

export default function RegistrationPanel() {
    const [toolInfo, setToolInfo] = useState(null)
    const [registrations, setRegistrations] = useState([])
    const [form, setForm] = useState(EMPTY_MANUAL)
    const [editingId, setEditingId] = useState(null)
    const [loading, setLoading] = useState(false)
    const [toast, setToast] = useState(null)

    const notify = (msg, ok = true) => {
        setToast({ msg, ok })
        setTimeout(() => setToast(null), 3500)
    }

    const load = async () => {
        try {
            const [info, regs] = await Promise.all([
                api.get('/api/admin/registrations/tool-info').then(r => r.data),
                api.get('/api/admin/registrations').then(r => r.data),
            ])
            setToolInfo(info)
            setRegistrations(regs)
        } catch { /* not in admin session */ }
    }

    useEffect(() => { load() }, [])

    const setField = (k, v) => setForm(f => ({ ...f, [k]: v }))

    const submit = async (e) => {
        e.preventDefault()
        setLoading(true)
        try {
            if (editingId) {
                await api.patch(`/api/admin/registrations/${editingId}`, form)
                notify('✅ Registro actualizado correctamente')
            } else {
                await api.post('/api/admin/registrations', form)
                notify('✅ Bloque LTI registrado — ya puede lanzarse desde Open edX')
            }
            setForm(EMPTY_MANUAL)
            setEditingId(null)
            load()
        } catch (err) {
            notify('❌ ' + (err.response?.data?.detail || 'Error al registrar'), false)
        } finally { setLoading(false) }
    }

    const startEdit = (r) => {
        setForm({
            label: r.label, issuer: r.issuer, client_id: r.client_id,
            deployment_id: r.deployment_id, keyset_url: r.keyset_url,
            auth_endpoint: r.auth_endpoint, token_endpoint: r.token_endpoint || '',
        })
        setEditingId(r.id)
        window.scrollTo({ top: 0, behavior: 'smooth' })
    }

    const cancelEdit = () => { setForm(EMPTY_MANUAL); setEditingId(null) }

    const toggleReg = async (id, label, isActive) => {
        try {
            await api.patch(`/api/admin/registrations/${id}/toggle`)
            notify(isActive ? `"${label}" desactivado` : `"${label}" activado`)
            load()
        } catch { notify('Error al cambiar estado', false) }
    }

    const deleteReg = async (id, label) => {
        if (!confirm(`¿Eliminar permanentemente "${label}"?`)) return
        try {
            await api.delete(`/api/admin/registrations/${id}`)
            notify('🗑️ Registro eliminado')
            load()
        } catch { notify('Error al eliminar', false) }
    }

    return (
        <div className="instructor-panel">
            <div className="panel-content">

                {/* ── PASO 1: URLs del tool ── */}
                {toolInfo && (
                    <div className="section-card">
                        <div className="section-card__title">
                            <span style={badgeStyle}>1</span>
                            Configura estas URLs en Open edX Studio <span style={{ fontSize: 11, color: 'var(--text-muted)', fontWeight: 400 }}>(igual para todos los bloques)</span>
                        </div>
                        <p style={hintText}>
                            Abre cada bloque LTI Consumer en Studio → haz clic en <strong>Editar</strong> → pestaña <strong>LTI 1.3</strong> → pega estos valores:
                        </p>
                        <FieldRow label="Tool Launch URL" value={toolInfo.tool_launch_url}
                            hint="→ campo «Tool Launch URL» en Studio" />
                        <FieldRow label="Tool Initiate Login URL" value={toolInfo.tool_initiate_login_url}
                            hint="→ campo «Tool Initiate Login URL» en Studio" />
                        <FieldRow label="Registered Redirect URIs" value={toolInfo.registered_redirect_uri}
                            hint="→ campo «Registered Redirect URIs» en Studio" />
                        <FieldRow label="Key Set URL (JWKS)" value={toolInfo.jwks_key_set_url}
                            hint="→ campo «Tool Public Key Set URL» o «Key Set URL» en Studio" />
                    </div>
                )}

                {/* ── PASO 2: Registro manual de cada bloque ── */}
                <div className="section-card" style={{ border: '1px solid rgba(99,102,241,0.4)', background: 'rgba(99,102,241,0.04)' }}>
                    <div className="section-card__title">
                        <span style={badgeStyle}>2</span>
                        {editingId ? '✏️ Editar registro de bloque LTI' : 'Registrar bloque LTI manualmente'}
                    </div>

                    <div style={{ background: 'rgba(234,179,8,0.08)', border: '1px solid rgba(234,179,8,0.25)', borderRadius: 'var(--radius-sm)', padding: '10px 12px', marginBottom: 14 }}>
                        <div style={{ fontSize: 11, fontWeight: 600, color: '#fbbf24', marginBottom: 4 }}>
                            ¿Dónde obtengo estos datos?
                        </div>
                        <p style={{ fontSize: 11, color: 'var(--text-muted)', margin: 0, lineHeight: 1.6 }}>
                            En Open edX Studio → bloque LTI Consumer → <strong>Editar</strong> → pestaña <strong>LTI 1.3</strong>.
                            Verás una sección <em>"LTI 1.3 Information"</em> con el <strong>Client ID</strong> y la <strong>Keyset URL</strong> únicos de ese bloque.
                            Copia esos valores en el formulario de abajo.
                        </p>
                    </div>

                    <form onSubmit={submit}>
                        <div className="form-group">
                            <label className="form-label">Nombre descriptivo del bloque</label>
                            <input className="form-input" placeholder="ej. Tutor Álgebra — Semana 3"
                                value={form.label} onChange={e => setField('label', e.target.value)} required />
                        </div>

                        <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 10 }}>
                            <div className="form-group">
                                <label className="form-label">Issuer (URL base de Open edX)</label>
                                <input className="form-input" placeholder="http://local.openedx.io"
                                    value={form.issuer} onChange={e => setField('issuer', e.target.value)} required />
                            </div>
                            <div className="form-group">
                                <label className="form-label">Deployment ID</label>
                                <input className="form-input" placeholder="1"
                                    value={form.deployment_id} onChange={e => setField('deployment_id', e.target.value)} />
                            </div>
                        </div>

                        <div className="form-group">
                            <label className="form-label">
                                Client ID
                                <span style={fieldHint}>← campo «LTI 1.3 Client ID» en Studio</span>
                            </label>
                            <input className="form-input" placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
                                value={form.client_id} onChange={e => setField('client_id', e.target.value)} required />
                        </div>

                        <div className="form-group">
                            <label className="form-label">
                                Keyset URL
                                <span style={fieldHint}>← campo «LTI 1.3 Keyset URL» en Studio — único por bloque</span>
                            </label>
                            <input className="form-input"
                                placeholder="http://local.openedx.io/api/lti_consumer/v1/public_keysets/block-v1:..."
                                value={form.keyset_url} onChange={e => setField('keyset_url', e.target.value)} required />
                        </div>

                        <div className="form-group">
                            <label className="form-label">
                                Auth Endpoint
                                <span style={fieldHint}>← campo «LTI 1.3 OIDC Callback URL» en Studio</span>
                            </label>
                            <input className="form-input"
                                placeholder="http://local.openedx.io/api/lti_consumer/v1/launch/"
                                value={form.auth_endpoint} onChange={e => setField('auth_endpoint', e.target.value)} required />
                        </div>

                        <div className="form-group">
                            <label className="form-label">
                                Token Endpoint
                                <span style={fieldHint}>← campo «LTI 1.3 Access Token URL» en Studio</span>
                            </label>
                            <input className="form-input"
                                placeholder="http://local.openedx.io/api/lti_consumer/v1/token/"
                                value={form.token_endpoint} onChange={e => setField('token_endpoint', e.target.value)} />
                        </div>

                        <div style={{ display: 'flex', gap: 10, marginTop: 4 }}>
                            <button className="btn-primary" type="submit" disabled={loading}>
                                {loading ? 'Guardando…' : editingId ? '💾 Actualizar registro' : '➕ Registrar bloque'}
                            </button>
                            {editingId && (
                                <button type="button" onClick={cancelEdit}
                                    style={{ padding: '8px 16px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border)', background: 'transparent', color: 'var(--text-secondary)', cursor: 'pointer', fontSize: 13 }}>
                                    Cancelar
                                </button>
                            )}
                        </div>
                    </form>
                </div>

                {/* ── Lista de bloques registrados ── */}
                {registrations.length > 0 && (
                    <div className="section-card">
                        <div className="section-card__title">
                            Bloques registrados ({registrations.length})
                        </div>
                        {registrations.map(r => (
                            <div key={r.id} style={{
                                padding: '10px 12px', background: 'var(--bg-elevated)',
                                borderRadius: 'var(--radius-sm)', marginBottom: 8,
                                border: `1px solid ${r.is_active ? 'rgba(99,102,241,0.2)' : 'rgba(239,68,68,0.2)'}`,
                            }}>
                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8 }}>
                                    <div style={{ flex: 1, minWidth: 0 }}>
                                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                                            <span style={{ fontWeight: 600, fontSize: 13 }}>{r.label}</span>
                                            <span style={{ fontSize: 10, color: r.is_active ? '#4ade80' : '#f87171', fontWeight: 600 }}>
                                                ● {r.is_active ? 'ACTIVO' : 'INACTIVO'}
                                            </span>
                                            {r.label.startsWith('Auto:') && (
                                                <span style={{ fontSize: 10, background: 'rgba(99,102,241,0.15)', color: 'var(--accent-primary)', padding: '1px 6px', borderRadius: 10 }}>auto</span>
                                            )}
                                        </div>
                                        <div style={{ fontFamily: 'monospace', fontSize: 10, color: 'var(--text-muted)', marginTop: 3 }}>
                                            client_id: {r.client_id}
                                        </div>
                                        <div style={{ fontFamily: 'monospace', fontSize: 10, color: 'var(--text-muted)', marginTop: 1, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                                            keyset: {r.keyset_url}
                                        </div>
                                    </div>
                                    <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
                                        <button style={btnEdit} onClick={() => startEdit(r)}>✏️</button>
                                        <button
                                            style={{ ...btnSmall, color: r.is_active ? '#fbbf24' : '#4ade80', borderColor: r.is_active ? 'rgba(251,191,36,0.4)' : 'rgba(74,222,128,0.4)' }}
                                            onClick={() => toggleReg(r.id, r.label, r.is_active)}
                                        >
                                            {r.is_active ? '⏸' : '▶'}
                                        </button>
                                        <button style={btnDanger} onClick={() => deleteReg(r.id, r.label)}>🗑️</button>
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>
                )}

            </div>

            {toast && (
                <div className="toast" style={{ background: toast.ok ? '#064e3b' : '#7f1d1d', borderColor: toast.ok ? '#065f46' : '#991b1b', color: toast.ok ? '#6ee7b7' : '#fca5a5' }}>
                    {toast.msg}
                </div>
            )}
        </div>
    )
}

// ── Styles ────────────────────────────────────────────────────────────────────
const badgeStyle = {
    background: 'var(--accent-primary)', color: 'white',
    borderRadius: '50%', width: 22, height: 22,
    display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
    fontSize: 12, marginRight: 8,
}

const hintText = {
    fontSize: '12px', color: 'var(--text-secondary)', lineHeight: 1.6, margin: '0 0 12px',
}

const fieldHint = {
    marginLeft: 6, fontSize: 10, color: 'var(--accent-primary)', fontWeight: 400,
}

const btnSmall = {
    fontSize: 11, padding: '3px 8px', borderRadius: 4,
    border: '1px solid', cursor: 'pointer', background: 'transparent',
}

const btnEdit = {
    ...btnSmall, color: 'var(--text-secondary)', borderColor: 'var(--border)',
}

const btnDanger = {
    ...btnSmall, color: '#f87171', borderColor: 'rgba(239,68,68,0.4)',
}
