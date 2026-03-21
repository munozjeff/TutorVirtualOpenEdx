import { useState, useEffect, useRef } from 'react'
import { configApi, documentsApi, challengesApi } from '../api/client'

export default function InstructorView({ config, onConfigUpdate, onClearHistory, userInfo }) {
    const [form, setForm] = useState({
        tutor_name: config?.tutor_name || '',
        topic: config?.topic || '',
        system_prompt: config?.system_prompt || '',
        welcome_message: config?.welcome_message || '',
        mode: config?.mode || 'libre',
    })
    const [sharingForm, setSharingForm] = useState({
        share_context: config?.share_context || false,
        share_group_id: config?.share_group_id || '',
    })
    const [documents, setDocuments] = useState([])
    const [uploading, setUploading] = useState(false)
    const [uploadProgress, setUploadProgress] = useState(0)
    const [isSaving, setIsSaving] = useState(false)
    const [toast, setToast] = useState(null)
    const fileInputRef = useRef(null)

    // Challenges state
    const [challenges, setChallenges] = useState([])
    const [challengeForm, setChallengeForm] = useState({ title: '', question: '', answer_guide: '', order: 0 })
    const [editingChallenge, setEditingChallenge] = useState(null) // id being edited
    const [showChallengeForm, setShowChallengeForm] = useState(false)
    const [generateForm, setGenerateForm] = useState({ topic: '', difficulty: 'medio', count: 1 })
    const [isGenerating, setIsGenerating] = useState(false)

    const showToast = (msg, ok = true) => {
        setToast({ msg, ok })
        setTimeout(() => setToast(null), 3500)
    }

    // Load documents when mode is rag or on mount
    const loadDocuments = async () => {
        try {
            const docs = await documentsApi.list()
            setDocuments(docs)
        } catch { /* ignore */ }
    }

    const loadChallenges = async () => {
        try {
            const list = await challengesApi.list()
            setChallenges(list)
        } catch { /* ignore */ }
    }

    useEffect(() => { loadDocuments(); loadChallenges() }, [])

    // Challenge handlers
    const handleOpenNewChallenge = () => {
        setEditingChallenge(null)
        setChallengeForm({ title: '', question: '', answer_guide: '', order: challenges.length })
        setShowChallengeForm(true)
    }

    const handleEditChallenge = (c) => {
        setEditingChallenge(c.id)
        setChallengeForm({ title: c.title, question: c.question, answer_guide: c.answer_guide, order: c.order })
        setShowChallengeForm(true)
    }

    const handleSaveChallenge = async () => {
        try {
            if (editingChallenge) {
                const updated = await challengesApi.update(editingChallenge, challengeForm)
                setChallenges(prev => prev.map(c => c.id === editingChallenge ? updated : c))
            } else {
                const created = await challengesApi.create(challengeForm)
                setChallenges(prev => [...prev, created])
            }
            setShowChallengeForm(false)
            setEditingChallenge(null)
            showToast('✅ Desafío guardado')
        } catch {
            showToast('❌ Error al guardar desafío', false)
        }
    }

    const handleDeleteChallenge = async (id, title) => {
        if (!confirm(`¿Eliminar el desafío "${title || 'sin título'}"?`)) return
        try {
            await challengesApi.delete(id)
            setChallenges(prev => prev.filter(c => c.id !== id))
            showToast('🗑️ Desafío eliminado')
        } catch {
            showToast('❌ Error al eliminar', false)
        }
    }

    const handleGenerate = async () => {
        if (!generateForm.topic.trim()) { showToast('❌ Ingresa un tema', false); return }
        setIsGenerating(true)
        try {
            const generated = await challengesApi.generate(generateForm)
            setChallenges(prev => [...prev, ...generated])
            setGenerateForm({ topic: '', difficulty: 'medio', count: 1 })
            showToast(`✅ ${generated.length} desafío(s) generado(s) con IA`)
        } catch (err) {
            showToast('❌ ' + (err.response?.data?.detail || 'Error al generar'), false)
        } finally {
            setIsGenerating(false)
        }
    }

    // Keep form in sync if parent config changes
    useEffect(() => {
        if (config) {
            setForm({
                tutor_name: config.tutor_name || '',
                topic: config.topic || '',
                system_prompt: config.system_prompt || '',
                welcome_message: config.welcome_message || '',
                mode: config.mode || 'libre',
            })
            setSharingForm({
                share_context: config.share_context || false,
                share_group_id: config.share_group_id || '',
            })
        }
    }, [config])

    const handleSaveConfig = async () => {
        setIsSaving(true)
        try {
            const updated = await configApi.updateConfig(form)
            onConfigUpdate(updated)
            showToast('✅ Configuración guardada')
        } catch {
            showToast('❌ Error al guardar', false)
        } finally {
            setIsSaving(false)
        }
    }

    const handleSaveSharing = async () => {
        setIsSaving(true)
        try {
            const updated = await configApi.updateSharing({
                share_context: sharingForm.share_context,
                share_group_id: sharingForm.share_group_id || null,
            })
            onConfigUpdate(updated)
            showToast('✅ Configuración de contexto guardada')
        } catch {
            showToast('❌ Error al guardar', false)
        } finally {
            setIsSaving(false)
        }
    }

    const handleUpload = async (e) => {
        const file = e.target.files?.[0]
        if (!file) return
        if (!file.name.toLowerCase().endsWith('.pdf')) {
            showToast('❌ Solo se permiten archivos PDF', false)
            return
        }
        setUploading(true)
        setUploadProgress(0)
        try {
            const doc = await documentsApi.upload(file, (evt) => {
                if (evt.total) setUploadProgress(Math.round(evt.loaded / evt.total * 100))
            })
            setDocuments(prev => [doc, ...prev])
            showToast(`✅ "${doc.filename}" procesado — ${doc.chunk_count} fragmentos indexados`)
        } catch (err) {
            showToast('❌ ' + (err.response?.data?.detail || 'Error al subir el archivo'), false)
        } finally {
            setUploading(false)
            setUploadProgress(0)
            if (fileInputRef.current) fileInputRef.current.value = ''
        }
    }

    const handleDeleteDoc = async (doc) => {
        if (!confirm(`¿Eliminar "${doc.filename}"? Se perderán todos sus fragmentos indexados.`)) return
        try {
            await documentsApi.delete(doc.id)
            setDocuments(prev => prev.filter(d => d.id !== doc.id))
            showToast(`🗑️ "${doc.filename}" eliminado`)
        } catch {
            showToast('❌ Error al eliminar', false)
        }
    }

    const formatSize = (bytes) => {
        if (bytes < 1024) return `${bytes} B`
        if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
        return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
    }

    return (
        <div className="instructor-panel">
            <div className="panel-content">

                {/* ── Instance Info ── */}
                <div className="section-card">
                    <div className="section-card__title">🔗 Información de la Instancia</div>
                    <div className="info-row">
                        <span className="info-row__label">Instance ID</span>
                        <span className="info-row__value">{config?.instance_id}</span>
                    </div>
                    <div className="info-row">
                        <span className="info-row__label">Resource Link ID</span>
                        <span className="info-row__value">{config?.resource_link_id?.substring(0, 32)}…</span>
                    </div>
                    <div className="info-row">
                        <span className="info-row__label">Contexto / Curso</span>
                        <span className="info-row__value">{config?.context_id?.substring(0, 32)}…</span>
                    </div>
                    <div className="info-row">
                        <span className="info-row__label">Instructor</span>
                        <span className="info-row__value">{userInfo?.user_name} ({userInfo?.user_email})</span>
                    </div>
                </div>

                {/* ── Modo de funcionamiento ── */}
                <div className="section-card" style={{ border: '1px solid rgba(99,102,241,0.3)' }}>
                    <div className="section-card__title">⚙️ Modo de Funcionamiento</div>
                    <p style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 14, lineHeight: 1.6 }}>
                        Selecciona cómo responderá el tutor en esta instancia.
                    </p>
                    <div style={{ display: 'flex', gap: 12 }}>
                        {[
                            { value: 'libre', label: '💬 Modo Libre', desc: 'El modelo responde libremente con su conocimiento general.' },
                            { value: 'rag', label: '📚 Modo RAG', desc: 'El modelo responde basándose en los documentos cargados para este curso.' },
                        ].map(opt => (
                            <label key={opt.value} onClick={() => setForm(f => ({ ...f, mode: opt.value }))} style={{
                                flex: 1, padding: '12px 14px', borderRadius: 'var(--radius-sm)',
                                border: `2px solid ${form.mode === opt.value ? 'var(--accent-primary)' : 'var(--border)'}`,
                                background: form.mode === opt.value ? 'rgba(99,102,241,0.08)' : 'var(--bg-elevated)',
                                cursor: 'pointer', transition: 'all 0.15s',
                            }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                                    <input type="radio" name="mode" value={opt.value} checked={form.mode === opt.value} onChange={() => {}} style={{ accentColor: 'var(--accent-primary)' }} />
                                    <span style={{ fontWeight: 600, fontSize: 13 }}>{opt.label}</span>
                                </div>
                                <p style={{ fontSize: 11, color: 'var(--text-muted)', margin: 0, lineHeight: 1.5 }}>{opt.desc}</p>
                            </label>
                        ))}
                    </div>
                    <button className="btn-primary" onClick={handleSaveConfig} disabled={isSaving} style={{ marginTop: 14 }}>
                        {isSaving ? 'Guardando…' : 'Guardar modo'}
                    </button>
                </div>

                {/* ── Documentos RAG (solo visible cuando modo=rag) ── */}
                {form.mode === 'rag' && (
                    <div className="section-card" style={{ border: '1px solid rgba(99,102,241,0.3)' }}>
                        <div className="section-card__title">📄 Documentos del Curso</div>
                        <p style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 14, lineHeight: 1.6 }}>
                            Los PDFs que subas aquí estarán disponibles para <strong>todos los bloques de este curso</strong>.
                            El tutor usará su contenido para responder en modo RAG.
                        </p>

                        {/* Upload area */}
                        <div
                            onClick={() => !uploading && fileInputRef.current?.click()}
                            style={{
                                border: '2px dashed var(--border)', borderRadius: 'var(--radius-sm)',
                                padding: '20px', textAlign: 'center', cursor: uploading ? 'default' : 'pointer',
                                background: 'var(--bg-elevated)', marginBottom: 14,
                                opacity: uploading ? 0.7 : 1, transition: 'border-color 0.15s',
                            }}
                            onMouseEnter={e => { if (!uploading) e.currentTarget.style.borderColor = 'var(--accent-primary)' }}
                            onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--border)' }}
                        >
                            <input ref={fileInputRef} type="file" accept=".pdf" onChange={handleUpload} style={{ display: 'none' }} />
                            {uploading ? (
                                <div>
                                    <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 8 }}>
                                        Procesando PDF… {uploadProgress > 0 ? `${uploadProgress}%` : ''}
                                    </div>
                                    <div style={{ height: 6, background: 'var(--border)', borderRadius: 3, overflow: 'hidden' }}>
                                        <div style={{ height: '100%', width: `${uploadProgress || 30}%`, background: 'var(--accent-primary)', borderRadius: 3, transition: 'width 0.3s', animation: uploadProgress === 0 ? 'pulse 1.5s infinite' : 'none' }} />
                                    </div>
                                    <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 6 }}>
                                        Extrayendo texto y generando embeddings…
                                    </div>
                                </div>
                            ) : (
                                <>
                                    <div style={{ fontSize: 28, marginBottom: 6 }}>📎</div>
                                    <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-primary)' }}>
                                        Haz clic para subir un PDF
                                    </div>
                                    <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4 }}>
                                        Máximo 20 MB por archivo
                                    </div>
                                </>
                            )}
                        </div>

                        {/* Document list */}
                        {documents.length === 0 ? (
                            <p style={{ fontSize: 12, color: 'var(--text-muted)', textAlign: 'center', padding: '12px 0' }}>
                                No hay documentos cargados para este curso.
                            </p>
                        ) : (
                            <div>
                                <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: 8 }}>
                                    {documents.length} documento{documents.length !== 1 ? 's' : ''} indexado{documents.length !== 1 ? 's' : ''}
                                </div>
                                {documents.map(doc => (
                                    <div key={doc.id} style={{
                                        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                                        padding: '9px 12px', background: 'var(--bg-elevated)',
                                        borderRadius: 'var(--radius-sm)', marginBottom: 6,
                                        border: '1px solid var(--border)',
                                    }}>
                                        <div style={{ flex: 1, minWidth: 0 }}>
                                            <div style={{ fontWeight: 500, fontSize: 13, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                                📄 {doc.filename}
                                            </div>
                                            <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 2 }}>
                                                {formatSize(doc.file_size)} · {doc.chunk_count} fragmentos · subido por {doc.uploaded_by}
                                            </div>
                                        </div>
                                        <button
                                            onClick={() => handleDeleteDoc(doc)}
                                            style={{ marginLeft: 10, fontSize: 11, padding: '3px 8px', borderRadius: 4, border: '1px solid rgba(239,68,68,0.4)', cursor: 'pointer', background: 'transparent', color: '#f87171', flexShrink: 0 }}
                                        >
                                            🗑️
                                        </button>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                )}

                {/* ── Desafíos ── */}
                <div className="section-card" style={{ border: '1px solid rgba(251,191,36,0.3)' }}>
                    <div className="section-card__title">🏆 Desafíos</div>
                    <p style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 14, lineHeight: 1.6 }}>
                        Los desafíos se presentan al estudiante cuando abre este bloque. El tutor usa el método socrático si la respuesta es incorrecta.
                        Si los bloques comparten contexto, el historial de desafíos también se comparte.
                    </p>

                    {/* Challenge list */}
                    {challenges.length === 0 ? (
                        <p style={{ fontSize: 12, color: 'var(--text-muted)', textAlign: 'center', padding: '8px 0' }}>
                            No hay desafíos configurados. Crea uno manualmente o genera con IA.
                        </p>
                    ) : (
                        <div style={{ marginBottom: 12 }}>
                            {challenges.map((c, i) => (
                                <div key={c.id} style={{
                                    padding: '10px 12px', background: 'var(--bg-elevated)',
                                    borderRadius: 'var(--radius-sm)', marginBottom: 6,
                                    border: '1px solid var(--border)',
                                    display: 'flex', gap: 10, alignItems: 'flex-start',
                                }}>
                                    <div style={{ fontSize: 18, lineHeight: 1, paddingTop: 2, flexShrink: 0 }}>🎯</div>
                                    <div style={{ flex: 1, minWidth: 0 }}>
                                        <div style={{ fontWeight: 600, fontSize: 13 }}>
                                            #{i + 1} {c.title || '(sin título)'}
                                        </div>
                                        <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 2, lineHeight: 1.4 }}>
                                            {c.question.length > 120 ? c.question.substring(0, 120) + '…' : c.question}
                                        </div>
                                        {c.answer_guide && (
                                            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4 }}>
                                                🔑 Guía: {c.answer_guide.length > 80 ? c.answer_guide.substring(0, 80) + '…' : c.answer_guide}
                                            </div>
                                        )}
                                    </div>
                                    <div style={{ display: 'flex', gap: 4, flexShrink: 0 }}>
                                        <button onClick={() => handleEditChallenge(c)} style={{ fontSize: 11, padding: '3px 7px', borderRadius: 4, border: '1px solid var(--border)', cursor: 'pointer', background: 'transparent', color: 'var(--text-secondary)' }}>✏️</button>
                                        <button onClick={() => handleDeleteChallenge(c.id, c.title)} style={{ fontSize: 11, padding: '3px 7px', borderRadius: 4, border: '1px solid rgba(239,68,68,0.4)', cursor: 'pointer', background: 'transparent', color: '#f87171' }}>🗑️</button>
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}

                    {/* Form: create/edit */}
                    {showChallengeForm && (
                        <div style={{ background: 'var(--bg-elevated)', borderRadius: 'var(--radius-sm)', padding: 14, border: '1px solid rgba(251,191,36,0.3)', marginBottom: 12 }}>
                            <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 10 }}>
                                {editingChallenge ? '✏️ Editar desafío' : '➕ Nuevo desafío'}
                            </div>
                            <div className="form-group">
                                <label className="form-label">Título (opcional)</label>
                                <input className="form-input" value={challengeForm.title}
                                    onChange={e => setChallengeForm(f => ({ ...f, title: e.target.value }))}
                                    placeholder="Ej: Concepto de Revolución Industrial" />
                            </div>
                            <div className="form-group">
                                <label className="form-label">Pregunta del desafío *</label>
                                <textarea className="form-textarea" rows={3} value={challengeForm.question}
                                    onChange={e => setChallengeForm(f => ({ ...f, question: e.target.value }))}
                                    placeholder="¿Cuáles fueron las principales causas de la Revolución Industrial?" />
                            </div>
                            <div className="form-group">
                                <label className="form-label">Guía de evaluación (solo para el tutor)</label>
                                <textarea className="form-textarea" rows={2} value={challengeForm.answer_guide}
                                    onChange={e => setChallengeForm(f => ({ ...f, answer_guide: e.target.value }))}
                                    placeholder="La respuesta debe mencionar: avance tecnológico, mano de obra, capitalismo..." />
                            </div>
                            <div style={{ display: 'flex', gap: 8 }}>
                                <button className="btn-primary" onClick={handleSaveChallenge} style={{ flex: 1 }}>
                                    {editingChallenge ? 'Actualizar' : 'Crear desafío'}
                                </button>
                                <button onClick={() => setShowChallengeForm(false)} style={{ padding: '8px 14px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border)', cursor: 'pointer', background: 'transparent', color: 'var(--text-secondary)', fontSize: 13 }}>
                                    Cancelar
                                </button>
                            </div>
                        </div>
                    )}

                    {/* Generate with AI */}
                    <div style={{ background: 'var(--bg-elevated)', borderRadius: 'var(--radius-sm)', padding: 12, border: '1px solid rgba(99,102,241,0.2)', marginBottom: 10 }}>
                        <div style={{ fontWeight: 600, fontSize: 12, color: 'var(--text-secondary)', marginBottom: 8 }}>✨ GENERAR CON IA</div>
                        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                            <input className="form-input" value={generateForm.topic} style={{ flex: 2, minWidth: 140 }}
                                onChange={e => setGenerateForm(f => ({ ...f, topic: e.target.value }))}
                                placeholder="Tema (ej: Revolución Industrial)" />
                            <select className="form-input" value={generateForm.difficulty} style={{ flex: 1, minWidth: 90 }}
                                onChange={e => setGenerateForm(f => ({ ...f, difficulty: e.target.value }))}>
                                <option value="fácil">Fácil</option>
                                <option value="medio">Medio</option>
                                <option value="difícil">Difícil</option>
                            </select>
                            <select className="form-input" value={generateForm.count} style={{ width: 60 }}
                                onChange={e => setGenerateForm(f => ({ ...f, count: Number(e.target.value) }))}>
                                {[1,2,3,4,5].map(n => <option key={n} value={n}>{n}</option>)}
                            </select>
                            <button className="btn-primary" onClick={handleGenerate} disabled={isGenerating} style={{ whiteSpace: 'nowrap' }}>
                                {isGenerating ? 'Generando…' : '✨ Generar'}
                            </button>
                        </div>
                    </div>

                    <button className="btn-primary" onClick={handleOpenNewChallenge} style={{ width: '100%', background: 'transparent', border: '1px dashed rgba(251,191,36,0.5)', color: 'var(--text-secondary)' }}>
                        + Añadir desafío manualmente
                    </button>
                </div>

                {/* ── Tutor Persona ── */}
                <div className="section-card">
                    <div className="section-card__title">🎭 Personalidad del Tutor</div>

                    <div className="form-group">
                        <label className="form-label">Nombre del Tutor</label>
                        <input className="form-input" value={form.tutor_name}
                            onChange={(e) => setForm({ ...form, tutor_name: e.target.value })}
                            placeholder="Ej: Tutor de Matemáticas" />
                    </div>

                    <div className="form-group">
                        <label className="form-label">Tema / Área</label>
                        <input className="form-input" value={form.topic}
                            onChange={(e) => setForm({ ...form, topic: e.target.value })}
                            placeholder="Ej: Álgebra Lineal" />
                    </div>

                    <div className="form-group">
                        <label className="form-label">Prompt del Sistema</label>
                        <textarea className="form-textarea" value={form.system_prompt}
                            onChange={(e) => setForm({ ...form, system_prompt: e.target.value })}
                            rows={4} placeholder="Eres un tutor experto en…" />
                    </div>

                    <div className="form-group">
                        <label className="form-label">Mensaje de Bienvenida</label>
                        <textarea className="form-textarea" value={form.welcome_message}
                            onChange={(e) => setForm({ ...form, welcome_message: e.target.value })}
                            rows={2} placeholder="¡Hola! ¿En qué puedo ayudarte?" />
                    </div>

                    <button className="btn-primary" onClick={handleSaveConfig} disabled={isSaving}>
                        {isSaving ? 'Guardando…' : 'Guardar Configuración'}
                    </button>
                </div>

                {/* ── Context Sharing ── */}
                <div className="section-card">
                    <div className="section-card__title">🔗 Compartir Contexto entre Instancias</div>

                    <div className="toggle-row">
                        <div className="toggle-info">
                            <span>Compartir historial</span>
                            <small>Si está activo, esta instancia comparte el chat del estudiante con otras del mismo grupo</small>
                        </div>
                        <label className="toggle">
                            <input type="checkbox" checked={sharingForm.share_context}
                                onChange={(e) => setSharingForm({ ...sharingForm, share_context: e.target.checked })} />
                            <span className="toggle__slider" />
                        </label>
                    </div>

                    {sharingForm.share_context && (
                        <div className="form-group" style={{ marginTop: '14px' }}>
                            <label className="form-label">ID de Grupo Compartido</label>
                            <input className="form-input" value={sharingForm.share_group_id}
                                onChange={(e) => setSharingForm({ ...sharingForm, share_group_id: e.target.value })}
                                placeholder="Ej: modulo-1" />
                        </div>
                    )}

                    <button className="btn-primary" onClick={handleSaveSharing} disabled={isSaving} style={{ marginTop: '14px' }}>
                        {isSaving ? 'Guardando…' : 'Guardar Configuración de Contexto'}
                    </button>
                </div>

                {/* ── Danger Zone ── */}
                <div className="section-card">
                    <div className="section-card__title">⚠️ Zona de Peligro</div>
                    <p style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '12px' }}>
                        Estas acciones afectan a todos los estudiantes de esta instancia.
                    </p>
                    <button className="btn-danger" onClick={onClearHistory}>
                        🗑️ Borrar historial de esta instancia (todos los estudiantes)
                    </button>
                </div>

            </div>

            {toast && (
                <div className="toast" style={{ background: toast.ok ? '#064e3b' : '#7f1d1d', borderColor: toast.ok ? '#065f46' : '#991b1b', color: toast.ok ? '#6ee7b7' : '#fca5a5' }}>
                    {toast.msg}
                </div>
            )}
        </div>
    )
}
