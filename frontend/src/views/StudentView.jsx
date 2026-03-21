import { useState, useEffect } from 'react'
import ChatWindow from '../components/ChatWindow'
import { challengesApi } from '../api/client'

export default function StudentView({ messages, isLoading, error, onSend }) {
    const [challengeStatus, setChallengeStatus] = useState(null)
    const [expanded, setExpanded] = useState(false)

    const loadStatus = async () => {
        try {
            const status = await challengesApi.getStatus()
            setChallengeStatus(status)
        } catch { /* no challenges configured */ }
    }

    useEffect(() => { loadStatus() }, [])

    const handleSend = async (msg) => {
        await onSend(msg)
        setTimeout(loadStatus, 800)
    }

    const hasChallenges = challengeStatus && challengeStatus.challenges.length > 0
    const allPassed = challengeStatus?.all_passed
    const currentId = challengeStatus?.current_challenge_id
    const currentChallenge = hasChallenges
        ? challengeStatus.challenges.find(c => c.id === currentId)
        : null
    const currentAttempt = hasChallenges && currentId
        ? challengeStatus.attempts.find(a => a.challenge_id === currentId)
        : null
    const passedCount = hasChallenges
        ? challengeStatus.attempts.filter(a => a.status === 'passed').length
        : 0
    const totalCount = hasChallenges ? challengeStatus.challenges.length : 0
    const siblingPending = challengeStatus?.sibling_pending || []
    const hasSiblingPending = siblingPending.length > 0

    const showBanner = hasChallenges || hasSiblingPending
    const accentColor = allPassed ? '#16a34a' : '#c00'

    return (
        <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>

            {/* ── Challenge bar (compact, collapsible) ─────────────────────── */}
            {showBanner && (
                <div style={{ flexShrink: 0, borderBottom: `1px solid ${allPassed ? '#d1fae5' : '#fde8e8'}` }}>

                    {/* Always-visible thin row */}
                    <button
                        onClick={() => setExpanded(v => !v)}
                        style={{
                            width: '100%',
                            display: 'flex',
                            alignItems: 'center',
                            gap: 10,
                            padding: '6px 14px',
                            background: allPassed ? '#f0faf4' : '#fff8f8',
                            border: 'none',
                            cursor: 'pointer',
                            textAlign: 'left',
                        }}
                    >
                        {/* Icon + label */}
                        <span style={{ fontSize: 13 }}>{allPassed ? '🎉' : '🏆'}</span>
                        <span style={{ fontSize: 11, fontWeight: 700, color: accentColor, textTransform: 'uppercase', letterSpacing: '0.4px', whiteSpace: 'nowrap' }}>
                            {allPassed
                                ? '¡Completado!'
                                : `Desafío ${passedCount + 1} de ${totalCount}`}
                        </span>

                        {/* Progress bar */}
                        <div style={{ flex: 1, height: 4, background: '#e5e5e5', borderRadius: 2, overflow: 'hidden' }}>
                            <div style={{
                                height: '100%',
                                width: `${totalCount > 0 ? (passedCount / totalCount) * 100 : 0}%`,
                                background: accentColor,
                                borderRadius: 2,
                                transition: 'width 0.4s ease',
                            }} />
                        </div>

                        {/* Sibling pending pill */}
                        {hasSiblingPending && (
                            <span style={{
                                fontSize: 10, fontWeight: 700, color: '#7c4f00',
                                background: '#fff3cd', border: '1px solid #f0a500',
                                borderRadius: 10, padding: '1px 7px', whiteSpace: 'nowrap',
                            }}>
                                ⚠️ {siblingPending.length} pendiente{siblingPending.length > 1 ? 's' : ''}
                            </span>
                        )}

                        {/* Chevron */}
                        <span style={{ fontSize: 10, color: '#aaa', transition: 'transform 0.2s', transform: expanded ? 'rotate(180deg)' : 'rotate(0deg)' }}>▼</span>
                    </button>

                    {/* Expanded panel */}
                    {expanded && (
                        <div style={{ padding: '0 14px 10px', background: allPassed ? '#f0faf4' : '#fff8f8' }}>

                            {/* Current challenge */}
                            {!allPassed && currentChallenge && (
                                <div style={{
                                    background: '#fff', borderRadius: 4, padding: '8px 11px',
                                    border: `1px solid #ffd0d0`, marginBottom: hasSiblingPending ? 8 : 0,
                                }}>
                                    {currentChallenge.title && (
                                        <div style={{ fontSize: 10, fontWeight: 700, color: '#c00', marginBottom: 3, textTransform: 'uppercase', letterSpacing: '0.4px' }}>
                                            {currentChallenge.title}
                                        </div>
                                    )}
                                    <div style={{ fontSize: 13, color: '#1c1c1c', lineHeight: 1.5 }}>
                                        {currentChallenge.question}
                                    </div>
                                    {currentAttempt && currentAttempt.attempts_count > 0 && (
                                        <div style={{ fontSize: 11, color: '#999', marginTop: 4 }}>
                                            Intentos: {currentAttempt.attempts_count}
                                        </div>
                                    )}
                                </div>
                            )}

                            {/* Sibling pending */}
                            {hasSiblingPending && (
                                <div>
                                    <div style={{ fontSize: 10, fontWeight: 700, color: '#7c4f00', textTransform: 'uppercase', letterSpacing: '0.4px', marginBottom: 5 }}>
                                        Pendientes de otros bloques
                                    </div>
                                    {siblingPending.map((sp, i) => (
                                        <div key={sp.challenge_id} style={{
                                            background: '#fff', borderRadius: 4, padding: '7px 11px',
                                            border: '1px solid #f0a500', marginTop: i > 0 ? 5 : 0,
                                        }}>
                                            {sp.title && (
                                                <div style={{ fontSize: 10, fontWeight: 700, color: '#7c4f00', marginBottom: 2, textTransform: 'uppercase', letterSpacing: '0.4px' }}>
                                                    {sp.title} — {sp.block_name}
                                                </div>
                                            )}
                                            <div style={{ fontSize: 13, color: '#1c1c1c', lineHeight: 1.5 }}>
                                                {sp.question}
                                            </div>
                                            {sp.attempts_count > 0 && (
                                                <div style={{ fontSize: 11, color: '#999', marginTop: 3 }}>
                                                    Intentos anteriores: {sp.attempts_count}
                                                </div>
                                            )}
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>
                    )}
                </div>
            )}

            {/* ── Chat ─────────────────────────────────────────────────────── */}
            <div style={{ flex: 1, minHeight: 0, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
                <ChatWindow
                    messages={messages}
                    isLoading={isLoading}
                    error={error}
                    onSend={handleSend}
                />
            </div>
        </div>
    )
}
