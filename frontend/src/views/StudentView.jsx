import { useState, useEffect } from 'react'
import ChatWindow from '../components/ChatWindow'
import { challengesApi } from '../api/client'

export default function StudentView({ messages, isLoading, error, onSend }) {
    const [challengeStatus, setChallengeStatus] = useState(null)

    const loadStatus = async () => {
        try {
            const status = await challengesApi.getStatus()
            setChallengeStatus(status)
        } catch { /* no challenges configured */ }
    }

    useEffect(() => { loadStatus() }, [])

    // Refresh challenge status after each message
    const handleSend = async (msg) => {
        await onSend(msg)
        // Small delay to let backend process the attempt
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

    return (
        <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>

            {/* ── Sibling pending challenges banner ────────────────────────── */}
            {hasSiblingPending && (
                <div style={{
                    padding: '10px 16px',
                    background: '#fff3cd',
                    borderBottom: '2px solid #f0a500',
                    flexShrink: 0,
                }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                        <span style={{ fontSize: 16 }}>⚠️</span>
                        <span style={{ fontSize: 12, fontWeight: 700, color: '#7c4f00', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                            Tienes {siblingPending.length} desafío{siblingPending.length > 1 ? 's' : ''} pendiente{siblingPending.length > 1 ? 's' : ''} de completar
                        </span>
                    </div>
                    {siblingPending.map((sp, i) => (
                        <div key={sp.challenge_id} style={{
                            background: '#fff',
                            borderRadius: 4,
                            padding: '7px 11px',
                            border: '1px solid #f0a500',
                            marginTop: i > 0 ? 6 : 0,
                        }}>
                            {sp.title && (
                                <div style={{ fontSize: 11, fontWeight: 700, color: '#7c4f00', marginBottom: 2, textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                                    {sp.title} — {sp.block_name}
                                </div>
                            )}
                            <div style={{ fontSize: 13, color: '#1c1c1c', lineHeight: 1.5 }}>
                                {sp.question}
                            </div>
                            {sp.attempts_count > 0 && (
                                <div style={{ fontSize: 11, color: '#888', marginTop: 3 }}>
                                    Intentos anteriores: {sp.attempts_count}
                                </div>
                            )}
                        </div>
                    ))}
                </div>
            )}

            {/* ── Challenge banner (current block) ─────────────────────────── */}
            {hasChallenges && (
                <div style={{
                    padding: '10px 16px',
                    background: allPassed ? '#f0faf4' : '#fff8f8',
                    borderBottom: `1px solid ${allPassed ? '#86efac' : '#ffd0d0'}`,
                    flexShrink: 0,
                }}>
                    {/* Progress bar */}
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: allPassed ? 0 : 8 }}>
                        <span style={{ fontSize: 14 }}>{allPassed ? '🎉' : '🏆'}</span>
                        <div style={{ flex: 1 }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3 }}>
                                <span style={{ fontSize: 11, fontWeight: 700, color: allPassed ? '#166534' : '#c00', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                                    {allPassed ? '¡Todos los desafíos completados!' : `Desafío ${passedCount + 1} de ${totalCount}`}
                                </span>
                                <span style={{ fontSize: 11, color: '#888' }}>
                                    {passedCount}/{totalCount} completados
                                </span>
                            </div>
                            <div style={{ height: 4, background: '#e5e5e5', borderRadius: 2, overflow: 'hidden' }}>
                                <div style={{
                                    height: '100%',
                                    width: `${totalCount > 0 ? (passedCount / totalCount) * 100 : 0}%`,
                                    background: allPassed ? '#16a34a' : '#c00',
                                    borderRadius: 2, transition: 'width 0.4s ease',
                                }} />
                            </div>
                        </div>
                    </div>

                    {/* Current challenge card */}
                    {!allPassed && currentChallenge && (
                        <div style={{
                            background: '#ffffff', borderRadius: 4, padding: '8px 12px',
                            border: '1px solid #ffd0d0',
                        }}>
                            {currentChallenge.title && (
                                <div style={{ fontSize: 11, fontWeight: 700, color: '#c00', marginBottom: 3, textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                                    {currentChallenge.title}
                                </div>
                            )}
                            <div style={{ fontSize: 13, color: '#1c1c1c', lineHeight: 1.5 }}>
                                {currentChallenge.question}
                            </div>
                            {currentAttempt && currentAttempt.attempts_count > 0 && (
                                <div style={{ fontSize: 11, color: '#888', marginTop: 4 }}>
                                    Intentos: {currentAttempt.attempts_count}
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
