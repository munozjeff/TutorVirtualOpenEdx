import { useState, useEffect } from 'react'
import ChatWindow from '../components/ChatWindow'
import { challengesApi } from '../api/client'

export default function StudentView({ messages, isLoading, error, onSend, userInfo, config, onClearHistory }) {
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

    return (
        <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>

            {/* ── Challenge banner ─────────────────────────────────────────── */}
            {hasChallenges && (
                <div style={{
                    padding: '10px 16px',
                    background: allPassed
                        ? 'linear-gradient(135deg, rgba(16,185,129,0.15), rgba(5,150,105,0.1))'
                        : 'linear-gradient(135deg, rgba(251,191,36,0.12), rgba(245,158,11,0.08))',
                    borderBottom: `1px solid ${allPassed ? 'rgba(16,185,129,0.25)' : 'rgba(251,191,36,0.25)'}`,
                    flexShrink: 0,
                }}>
                    {/* Progress bar */}
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: allPassed ? 0 : 8 }}>
                        <span style={{ fontSize: 14 }}>{allPassed ? '🎉' : '🏆'}</span>
                        <div style={{ flex: 1 }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3 }}>
                                <span style={{ fontSize: 11, fontWeight: 600, color: allPassed ? '#6ee7b7' : '#fcd34d', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                                    {allPassed ? '¡Todos los desafíos completados!' : `Desafío ${passedCount + 1} de ${totalCount}`}
                                </span>
                                <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                                    {passedCount}/{totalCount} completados
                                </span>
                            </div>
                            <div style={{ height: 4, background: 'rgba(255,255,255,0.1)', borderRadius: 2, overflow: 'hidden' }}>
                                <div style={{
                                    height: '100%',
                                    width: `${totalCount > 0 ? (passedCount / totalCount) * 100 : 0}%`,
                                    background: allPassed ? '#10b981' : '#f59e0b',
                                    borderRadius: 2, transition: 'width 0.4s ease',
                                }} />
                            </div>
                        </div>
                    </div>

                    {/* Current challenge card */}
                    {!allPassed && currentChallenge && (
                        <div style={{
                            background: 'rgba(0,0,0,0.2)', borderRadius: 6, padding: '8px 12px',
                            border: '1px solid rgba(251,191,36,0.2)',
                        }}>
                            {currentChallenge.title && (
                                <div style={{ fontSize: 11, fontWeight: 700, color: '#fcd34d', marginBottom: 3, textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                                    {currentChallenge.title}
                                </div>
                            )}
                            <div style={{ fontSize: 13, color: 'var(--text-primary)', lineHeight: 1.5 }}>
                                {currentChallenge.question}
                            </div>
                            {currentAttempt && currentAttempt.attempts_count > 0 && (
                                <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4 }}>
                                    Intentos: {currentAttempt.attempts_count}
                                </div>
                            )}
                        </div>
                    )}
                </div>
            )}

            {/* ── Chat ─────────────────────────────────────────────────────── */}
            <div style={{ flex: 1, minHeight: 0, overflow: 'hidden' }}>
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
