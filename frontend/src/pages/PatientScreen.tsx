import React, { useState, useEffect, useRef } from 'react'
import type { Language } from '../types'
import { VoiceRecorder } from '../components/VoiceRecorder'
import { registerPatient, sendTextMessage, sendAudioMessage, computeTriage, reportInactivity } from '../api/client'

const SPEECH_LANG: Record<Language, string> = { en: 'en-US', ur: 'ur-PK', ar: 'ar-SA' }

// Spec §39 — patient stops responding: warn + notify staff after this much silence
// following an AI Nurse question, without ever inventing a low-acuity result.
const INACTIVITY_TIMEOUT_MS = 60_000

function speak(text: string, language: Language) {
  try {
    if (!('speechSynthesis' in window)) return
    window.speechSynthesis.cancel()
    const utterance = new SpeechSynthesisUtterance(text)
    utterance.lang = SPEECH_LANG[language]
    window.speechSynthesis.speak(utterance)
  } catch {
    // Voice playback is a convenience feature — never let it break the conversation.
  }
}

const GREETINGS: Record<Language, string> = {
  en: "Hello. I am going to ask you a few questions so the clinical team can understand how urgently you need to be assessed.",
  ur: "السلام علیکم۔ میں آپ سے چند سوالات پوچھوں گا تاکہ طبی ٹیم سمجھ سکے کہ آپ کو کتنی جلدی دیکھا جانا چاہیے۔",
  ar: "مرحباً. سأطرح عليك بعض الأسئلة حتى يتمكن الفريق الطبي من فهم مدى الإلحاح في تقييم حالتك.",
}

const PLACEHOLDERS: Record<Language, string> = {
  en: "Type your response here...",
  ur: "یہاں اپنا جواب لکھیں...",
  ar: "اكتب ردك هنا...",
}

const LANG_LABELS: Record<Language, string> = {
  en: 'English', ur: 'اردو', ar: 'عربي',
}

export const PatientScreen: React.FC = () => {
  const [language, setLanguage] = useState<Language>('en')
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [patientAge, setPatientAge] = useState('')
  const [biologicalSex, setBiologicalSex] = useState('UNKNOWN')
  const [arrivalMethod, setArrivalMethod] = useState('walk-in')
  const [pregnancyStatus, setPregnancyStatus] = useState('UNKNOWN')
  const [registered, setRegistered] = useState(false)
  const [messages, setMessages] = useState<{ speaker: string; text: string }[]>([])
  const [inputText, setInputText] = useState('')
  const [loading, setLoading] = useState(false)
  const [triageComplete, setTriageComplete] = useState(false)
  const [triageResult, setTriageResult] = useState<any>(null)
  const [highAcuityAlert, setHighAcuityAlert] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [voiceEnabled, setVoiceEnabled] = useState(true)
  const inactivityTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const inactivityReported = useRef(false)

  const isRTL = language === 'ur' || language === 'ar'

  const resetInactivityTimer = (sessionIdOverride?: string) => {
    if (inactivityTimer.current) clearTimeout(inactivityTimer.current)
    inactivityReported.current = false
    const activeSessionId = sessionIdOverride || sessionId
    if (!activeSessionId || triageComplete) return
    inactivityTimer.current = setTimeout(async () => {
      if (inactivityReported.current) return
      inactivityReported.current = true
      try {
        await reportInactivity(activeSessionId)
      } catch {
        // Best-effort — the important thing is we don't block or crash the UI.
      }
      setError(
        language === 'ur' ? 'ایسا لگتا ہے آپ نے جواب نہیں دیا۔ ایک نرس کو مطلع کر دیا گیا ہے۔'
        : language === 'ar' ? 'يبدو أنك لم ترد. تم إخطار ممرضة.'
        : "It looks like you haven't responded. A nurse has been notified to check on you."
      )
    }, INACTIVITY_TIMEOUT_MS)
  }

  useEffect(() => {
    return () => { if (inactivityTimer.current) clearTimeout(inactivityTimer.current) }
  }, [])

  const handleRegister = async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await registerPatient({
        age: patientAge ? parseInt(patientAge) : undefined,
        biological_sex: biologicalSex,
        preferred_language: language,
        arrival_method: arrivalMethod,
        pregnancy_status: biologicalSex === 'F' ? pregnancyStatus : 'NOT_APPLICABLE',
      })
      setSessionId(res.data.session_id || res.data.id)
      setRegistered(true)
      setMessages([{ speaker: 'ai_nurse', text: GREETINGS[language] }])
      if (voiceEnabled) speak(GREETINGS[language], language)
      resetInactivityTimer(res.data.session_id || res.data.id)
    } catch (e: any) {
      // Never silently pretend registration succeeded — the patient would believe
      // they were triaged while nothing was recorded.
      setError(
        language === 'ur' ? 'رجسٹریشن ناکام ہو گئی۔ براہ کرم دوبارہ کوشش کریں یا نرس سے مدد لیں۔'
        : language === 'ar' ? 'فشل التسجيل. يرجى المحاولة مرة أخرى أو طلب مساعدة الممرضة.'
        : 'Registration failed. Please try again or ask a nurse for help.'
      )
    } finally {
      setLoading(false)
    }
  }

  const handleSendText = async () => {
    if (!inputText.trim() || !sessionId) return
    const text = inputText.trim()
    setInputText('')
    setMessages(prev => [...prev, { speaker: 'patient', text }])
    setLoading(true)
    setError(null)

    try {
      const res = await sendTextMessage(sessionId, text, language)
      const data = res.data

      if (data.next_question) {
        setMessages(prev => [...prev, { speaker: 'ai_nurse', text: data.next_question }])
        if (voiceEnabled) speak(data.next_question, language)
      }

      if (data.high_acuity_trigger) {
        setHighAcuityAlert(data.high_acuity_reason || 'High priority concern detected. A nurse will assist you immediately.')
      }

      if (data.conversation_complete) {
        await handleComputeTriage()
      } else {
        resetInactivityTimer()
      }
    } catch (e) {
      setError('Unable to send message. Please try again or call for assistance.')
    } finally {
      setLoading(false)
    }
  }

  const handleAudioComplete = async (blob: Blob) => {
    if (!sessionId) return
    setLoading(true)
    setMessages(prev => [...prev, { speaker: 'patient', text: '[Voice message...]' }])
    setError(null)

    try {
      const res = await sendAudioMessage(sessionId, blob, language)
      const data = res.data

      if (data.error === 'speech_recognition_failed') {
        setError('Could not understand audio. Please type your response.')
        setMessages(prev => prev.filter(m => m.text !== '[Voice message...]'))
        return
      }

      // Update placeholder with actual transcript
      setMessages(prev => [
        ...prev.filter(m => m.text !== '[Voice message...]'),
        { speaker: 'patient', text: data.original_text || '[Voice message]' }
      ])

      if (data.next_question) {
        setMessages(prev => [...prev, { speaker: 'ai_nurse', text: data.next_question }])
        if (voiceEnabled) speak(data.next_question, language)
      }

      if (data.high_acuity_trigger) {
        setHighAcuityAlert('High priority concern detected. A nurse will assist you immediately.')
      }

      if (data.conversation_complete) {
        await handleComputeTriage()
      } else {
        resetInactivityTimer()
      }
    } catch (e) {
      setError('Audio processing failed. Please type your response.')
    } finally {
      setLoading(false)
    }
  }

  const handleLiveTranscript = async (text: string) => {
    if (!sessionId || !text.trim()) return
    setMessages(prev => [...prev, { speaker: 'patient', text }])
    setLoading(true)
    setError(null)

    try {
      const res = await sendTextMessage(sessionId, text, language)
      const data = res.data

      if (data.next_question) {
        setMessages(prev => [...prev, { speaker: 'ai_nurse', text: data.next_question }])
        if (voiceEnabled) speak(data.next_question, language)
      }

      if (data.high_acuity_trigger) {
        setHighAcuityAlert(data.high_acuity_reason || 'High priority concern detected. A nurse will assist you immediately.')
      }

      if (data.conversation_complete) {
        await handleComputeTriage()
      } else {
        resetInactivityTimer()
      }
    } catch (e) {
      setError('Unable to process voice. Please try typing your response below.')
    } finally {
      setLoading(false)
    }
  }

  const handleComputeTriage = async () => {
    if (!sessionId) return
    if (inactivityTimer.current) clearTimeout(inactivityTimer.current)
    try {
      const res = await computeTriage(sessionId)
      setTriageResult(res.data)
      setTriageComplete(true)
    } catch (e) {
      setError('Triage computation failed. A nurse will assist you.')
    }
  }

  if (!registered) {
    return (
      <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: 24 }}>
        <div style={{ maxWidth: 460, width: '100%' }}>
          <div style={{ textAlign: 'center', marginBottom: 32 }}>
            <div style={{ fontSize: '3rem', marginBottom: 12 }}>🏥</div>
            <h1 style={{ fontSize: '2rem', fontWeight: 700, marginBottom: 8 }}>AI Nurse</h1>
            <p style={{ color: 'var(--text-muted)' }}>Patient Triage System</p>
          </div>

          <div className="card">
            {/* Language selection */}
            <div style={{ marginBottom: 20 }}>
              <label id="lang-label" style={{ display: 'block', marginBottom: 8, fontWeight: 600 }}>Select Language / زبان منتخب کریں / اختر اللغة</label>
              <div role="group" aria-labelledby="lang-label" style={{ display: 'flex', gap: 10 }}>
                {(['en', 'ur', 'ar'] as Language[]).map(lang => (
                  <button key={lang}
                    className={language === lang ? 'btn-primary' : 'btn-secondary'}
                    style={{ flex: 1 }}
                    aria-pressed={language === lang}
                    aria-label={`${LANG_LABELS[lang]} language`}
                    onClick={() => setLanguage(lang)}>
                    {LANG_LABELS[lang]}
                  </button>
                ))}
              </div>
            </div>

            <div style={{ marginBottom: 20 }}>
              <label htmlFor="patient-age" style={{ display: 'block', marginBottom: 8, fontWeight: 600 }}>
                {language === 'ur' ? 'عمر (سال)' : language === 'ar' ? 'العمر (سنوات)' : 'Age (years)'}
              </label>
              <input id="patient-age" type="number" placeholder="e.g. 45" value={patientAge}
                onChange={e => setPatientAge(e.target.value)} min="0" max="130"
                aria-label={language === 'ur' ? 'عمر' : language === 'ar' ? 'العمر' : 'Age in years'} />
            </div>

            <div style={{ marginBottom: 20 }}>
              <label htmlFor="patient-sex" style={{ display: 'block', marginBottom: 8, fontWeight: 600 }}>
                {language === 'ur' ? 'جنس' : language === 'ar' ? 'الجنس' : 'Biological Sex'}
              </label>
              <select id="patient-sex" value={biologicalSex} onChange={e => setBiologicalSex(e.target.value)}>
                <option value="UNKNOWN">{language === 'ur' ? 'بتانا نہیں چاہتے' : language === 'ar' ? 'تفضل عدم الذكر' : 'Prefer not to say'}</option>
                <option value="F">{language === 'ur' ? 'خاتون' : language === 'ar' ? 'أنثى' : 'Female'}</option>
                <option value="M">{language === 'ur' ? 'مرد' : language === 'ar' ? 'ذكر' : 'Male'}</option>
                <option value="OTHER">{language === 'ur' ? 'دیگر' : language === 'ar' ? 'آخر' : 'Other'}</option>
              </select>
            </div>

            {biologicalSex === 'F' && (
              <div style={{ marginBottom: 20 }}>
                <label htmlFor="pregnancy-status" style={{ display: 'block', marginBottom: 8, fontWeight: 600 }}>
                  {language === 'ur' ? 'کیا آپ حاملہ ہیں؟' : language === 'ar' ? 'هل أنتِ حامل؟' : 'Are you currently pregnant?'}
                </label>
                <select id="pregnancy-status" value={pregnancyStatus} onChange={e => setPregnancyStatus(e.target.value)}>
                  <option value="UNKNOWN">{language === 'ur' ? 'معلوم نہیں' : language === 'ar' ? 'غير معروف' : 'Not sure / prefer not to say'}</option>
                  <option value="NOT_PREGNANT">{language === 'ur' ? 'نہیں' : language === 'ar' ? 'لا' : 'No'}</option>
                  <option value="PREGNANT">{language === 'ur' ? 'ہاں' : language === 'ar' ? 'نعم' : 'Yes'}</option>
                </select>
              </div>
            )}

            <div style={{ marginBottom: 20 }}>
              <label htmlFor="arrival-method" style={{ display: 'block', marginBottom: 8, fontWeight: 600 }}>
                {language === 'ur' ? 'آپ کیسے پہنچے؟' : language === 'ar' ? 'كيف وصلت؟' : 'How did you arrive?'}
              </label>
              <select id="arrival-method" value={arrivalMethod} onChange={e => setArrivalMethod(e.target.value)}>
                <option value="walk-in">{language === 'ur' ? 'خود چل کر' : language === 'ar' ? 'سيرًا على الأقدام' : 'Walk-in'}</option>
                <option value="ambulance">{language === 'ur' ? 'ایمبولینس' : language === 'ar' ? 'سيارة إسعاف' : 'Ambulance'}</option>
                <option value="referred">{language === 'ur' ? 'ریفرل' : language === 'ar' ? 'إحالة' : 'Referred by another clinic'}</option>
              </select>
            </div>

            <button className="btn-primary" style={{ width: '100%', padding: '14px' }}
              onClick={handleRegister} disabled={loading}
              aria-label={language === 'ur' ? 'شروع کریں' : language === 'ar' ? 'ابدأ' : 'Begin Assessment'}>
              {loading ? 'Starting...' : language === 'ur' ? 'شروع کریں' : language === 'ar' ? 'ابدأ' : 'Begin Assessment'}
            </button>

            {error && (
              <div role="alert" style={{ marginTop: 16, padding: '10px 14px', background: '#7f1d1d', color: '#fca5a5', borderRadius: 8, fontSize: '0.9rem' }}>
                ⚠ {error}
              </div>
            )}
          </div>
        </div>
      </div>
    )
  }

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }} dir={isRTL ? 'rtl' : 'ltr'}>
      {/* Header */}
      <div style={{ background: 'var(--surface)', borderBottom: '1px solid var(--border)', padding: '12px 24px', display: 'flex', alignItems: 'center', gap: 12 }}>
        <div style={{ fontSize: '1.5rem' }}>🏥</div>
        <div style={{ fontWeight: 700, fontSize: '1.1rem' }}>AI Nurse</div>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8, alignItems: 'center' }}>
          <button
            style={{ padding: '4px 10px', fontSize: '0.85rem' }}
            className="btn-secondary"
            aria-pressed={voiceEnabled}
            aria-label={voiceEnabled ? 'Disable voice playback' : 'Enable voice playback'}
            title={voiceEnabled ? 'Voice playback on' : 'Voice playback off'}
            onClick={() => { setVoiceEnabled(v => !v); window.speechSynthesis?.cancel() }}>
            {voiceEnabled ? '🔊' : '🔇'}
          </button>
          {(['en', 'ur', 'ar'] as Language[]).map(lang => (
            <button key={lang} style={{ padding: '4px 12px', fontSize: '0.85rem' }}
              className={language === lang ? 'btn-primary' : 'btn-secondary'}
              aria-pressed={language === lang}
              aria-label={`Switch to ${LANG_LABELS[lang]}`}
              onClick={() => setLanguage(lang)}>
              {LANG_LABELS[lang]}
            </button>
          ))}
        </div>
      </div>

      {/* High acuity alert */}
      {highAcuityAlert && (
        <div role="alert" style={{ background: '#dc2626', color: 'white', padding: '16px 24px', fontWeight: 600, textAlign: 'center', fontSize: '1.1rem' }}>
          🚨 {highAcuityAlert}
        </div>
      )}

      {/* Chat area */}
      <div role="log" aria-live="polite" aria-label="Conversation with AI Nurse"
        style={{ flex: 1, overflowY: 'auto', padding: '24px', display: 'flex', flexDirection: 'column', gap: 16, maxWidth: 700, width: '100%', margin: '0 auto' }}>
        {messages.map((msg, i) => (
          <div key={i} style={{
            display: 'flex',
            justifyContent: msg.speaker === 'patient' ? (isRTL ? 'flex-start' : 'flex-end') : (isRTL ? 'flex-end' : 'flex-start'),
          }}>
            <div style={{
              maxWidth: '80%',
              background: msg.speaker === 'patient' ? '#3b82f6' : 'var(--surface)',
              border: msg.speaker === 'ai_nurse' ? '1px solid var(--border)' : 'none',
              borderRadius: 16,
              padding: '12px 16px',
              fontSize: '1rem',
              lineHeight: 1.5,
            }}>
              {msg.speaker === 'ai_nurse' && (
                <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: 4 }}>AI Nurse</div>
              )}
              {msg.text}
            </div>
          </div>
        ))}
        {loading && (
          <div style={{ color: 'var(--text-muted)', fontStyle: 'italic' }}>
            {language === 'ur' ? 'لوڈ ہو رہا ہے...' : language === 'ar' ? 'جاري التحميل...' : 'Processing...'}
          </div>
        )}
      </div>

      {/* Triage result */}
      {triageComplete && triageResult && (
        <div style={{ padding: 24, borderTop: '1px solid var(--border)' }}>
          <div className="card" style={{ maxWidth: 700, margin: '0 auto', textAlign: 'center' }}>
            <div style={{ fontWeight: 700, fontSize: '1.2rem', marginBottom: 8 }}>
              {language === 'ur' ? 'تشخیص مکمل ہوئی' : language === 'ar' ? 'اكتمل التقييم' : 'Assessment Complete'}
            </div>
            <div className={`severity-badge severity-${triageResult.ai_recommendation}`}
              style={{ display: 'inline-flex', fontSize: '1.4rem', padding: '12px 30px' }}>
              {triageResult.ai_recommendation}
            </div>
            <p style={{ marginTop: 12, color: 'var(--text-muted)' }}>
              {language === 'ur' ? 'نرس جلد آپ کو دیکھے گی۔' : language === 'ar' ? 'سيراك ممرض قريباً.' : 'A nurse will see you shortly.'}
            </p>
          </div>
        </div>
      )}

      {/* Error */}
      {error && (
        <div role="alert" style={{ padding: '12px 24px', background: '#7f1d1d', color: '#fca5a5', fontSize: '0.9rem' }}>
          ⚠ {error}
        </div>
      )}

      {/* Input area */}
      {!triageComplete && (
        <div style={{ background: 'var(--surface)', borderTop: '1px solid var(--border)', padding: '16px 24px' }}>
          <div style={{ maxWidth: 700, margin: '0 auto' }}>
            <VoiceRecorder
              onRecordingComplete={handleAudioComplete}
              onTranscriptReady={handleLiveTranscript}
              language={language}
              disabled={loading}
            />
            <div style={{ display: 'flex', gap: 10, marginTop: 16, alignItems: 'flex-end' }}>
              <div style={{ flex: 1, position: 'relative' }}>
                <div style={{ color: 'var(--text-muted)', fontSize: '0.78rem', textAlign: 'center', marginBottom: 6 }}>
                  {language === 'ur' ? 'یا لکھیں' : language === 'ar' ? 'أو اكتب' : 'or type below'}
                </div>
                <textarea
                  value={inputText}
                  onChange={e => setInputText(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSendText() } }}
                  placeholder={PLACEHOLDERS[language]}
                  aria-label={PLACEHOLDERS[language]}
                  rows={2}
                  dir={isRTL ? 'rtl' : 'ltr'}
                  disabled={loading}
                  style={{ resize: 'none' }}
                />
              </div>
              <button className="btn-primary" onClick={handleSendText}
                disabled={!inputText.trim() || loading}
                aria-label={language === 'ur' ? 'پیغام بھیجیں' : language === 'ar' ? 'إرسال الرسالة' : 'Send message'}
                style={{ height: 64 }}>
                {isRTL ? '←' : '→'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
