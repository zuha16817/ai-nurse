import React, { useState, useRef, useCallback } from 'react'

interface VoiceRecorderProps {
  onRecordingComplete: (blob: Blob) => void
  onTranscriptReady?: (text: string) => void
  disabled?: boolean
  language?: string
}

export const VoiceRecorder: React.FC<VoiceRecorderProps> = ({
  onRecordingComplete, onTranscriptReady, disabled, language = 'en'
}) => {
  const [isRecording, setIsRecording] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const mediaRef = useRef<MediaRecorder | null>(null)
  const recognitionRef = useRef<any>(null)
  const chunksRef = useRef<Blob[]>([])

  const startRecording = useCallback(async () => {
    setError(null)
    const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition

    if (SpeechRecognition && onTranscriptReady) {
      try {
        const recognition = new SpeechRecognition()
        recognition.continuous = false
        recognition.interimResults = false
        recognition.lang = language === 'ur' ? 'ur-PK' : language === 'ar' ? 'ar-SA' : 'en-US'

        recognition.onstart = () => setIsRecording(true)
        recognition.onresult = (e: any) => {
          const text = e.results[0][0].transcript
          if (text) onTranscriptReady(text)
        }
        recognition.onerror = (e: any) => {
          console.warn('WebSpeech error:', e.error)
          setError('Could not hear voice. Try again or type below.')
          setIsRecording(false)
        }
        recognition.onend = () => setIsRecording(false)

        recognitionRef.current = recognition
        recognition.start()
        return
      } catch (e) {
        console.warn('SpeechRecognition start failed, falling back to MediaRecorder')
      }
    }

    // Fallback to MediaRecorder audio blob
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const recorder = new MediaRecorder(stream)
      chunksRef.current = []

      recorder.ondataavailable = e => {
        if (e.data.size > 0) chunksRef.current.push(e.data)
      }
      recorder.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: 'audio/webm' })
        onRecordingComplete(blob)
        stream.getTracks().forEach(t => t.stop())
      }

      recorder.start()
      mediaRef.current = recorder
      setIsRecording(true)
    } catch (err) {
      setError('Microphone unavailable. Please type your response below.')
    }
  }, [onRecordingComplete, onTranscriptReady, language])

  const stopRecording = useCallback(() => {
    if (recognitionRef.current) {
      try { recognitionRef.current.stop() } catch (e) {}
    }
    if (mediaRef.current) {
      try { mediaRef.current.stop() } catch (e) {}
    }
    setIsRecording(false)
  }, [])

  return (
    <div style={{ textAlign: 'center' }}>
      {error && (
        <div role="alert" style={{ color: '#f87171', marginBottom: 12, fontSize: '0.9rem' }}>
          ⚠ {error}
        </div>
      )}
      <button
        className={isRecording ? 'btn-danger' : 'btn-primary'}
        onClick={isRecording ? stopRecording : startRecording}
        disabled={disabled}
        aria-pressed={isRecording}
        aria-label={isRecording ? 'Stop recording' : 'Start recording - speak your response'}
        style={{
          width: 100, height: 100, borderRadius: '50%',
          fontSize: '2.5rem', display: 'flex', alignItems: 'center',
          justifyContent: 'center', margin: '0 auto',
          animation: isRecording ? 'pulse 1.5s infinite' : 'none',
          boxShadow: isRecording ? '0 0 0 0 rgba(220,38,38,0.4)' : undefined,
        }}
        title={isRecording ? 'Stop recording' : 'Start recording'}
      >
        {isRecording ? '⏹' : '🎙'}
      </button>
      <p role="status" style={{ marginTop: 10, color: 'var(--text-muted)', fontSize: '0.85rem' }}>
        {isRecording ? 'Recording... tap to stop' : 'Tap to speak'}
      </p>
      <style>{`
        @keyframes pulse {
          0% { box-shadow: 0 0 0 0 rgba(220,38,38,0.5); }
          70% { box-shadow: 0 0 0 20px rgba(220,38,38,0); }
          100% { box-shadow: 0 0 0 0 rgba(220,38,38,0); }
        }
      `}</style>
    </div>
  )
}
