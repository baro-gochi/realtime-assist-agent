/**
 * @fileoverview STT 엔진 비교 페이지
 *
 * @description
 * Google Cloud STT와 ElevenLabs STT 엔진의 성능을 실시간으로 비교합니다.
 * - 두 엔진의 인식 결과를 나란히 표시
 * - 응답 시간 비교
 * - 고유명사/전문용어 인식률 비교
 */

import { useState, useRef, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { WebRTCClient } from './webrtc';
import './STTComparison.css';

function STTComparison() {
  // WebRTC 및 연결 상태
  const [isConnected, setIsConnected] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [dualSttEnabled, setDualSttEnabled] = useState(false);
  const [connectionStatus, setConnectionStatus] = useState('disconnected');

  // STT 결과
  const [googleResults, setGoogleResults] = useState([]);
  const [elevenlabsResults, setElevenlabsResults] = useState([]);

  // 현재 인식 중인 partial 결과 (실시간 표시용)
  const [googlePartial, setGooglePartial] = useState('');
  const [elevenlabsPartial, setElevenlabsPartial] = useState('');

  // 통계
  const [stats, setStats] = useState({
    google: { count: 0, avgLatency: 0, totalLatency: 0 },
    elevenlabs: { count: 0, avgLatency: 0, totalLatency: 0 }
  });

  // Refs
  const clientRef = useRef(null);
  const localVideoRef = useRef(null);
  const googleResultsRef = useRef(null);
  const elevenlabsResultsRef = useRef(null);

  // 자동 스크롤
  useEffect(() => {
    if (googleResultsRef.current) {
      googleResultsRef.current.scrollTop = googleResultsRef.current.scrollHeight;
    }
  }, [googleResults]);

  useEffect(() => {
    if (elevenlabsResultsRef.current) {
      elevenlabsResultsRef.current.scrollTop = elevenlabsResultsRef.current.scrollHeight;
    }
  }, [elevenlabsResults]);

  // WebRTC 클라이언트 초기화
  useEffect(() => {
    const client = new WebRTCClient();
    clientRef.current = client;

    // 연결 상태 핸들러
    client.onConnectionStateChange = (state) => {
      console.log('Connection state:', state);
      setConnectionStatus(state);
      setIsConnected(state === 'connected');
    };

    // 로컬 스트림 핸들러
    client.onLocalStream = (stream) => {
      if (localVideoRef.current) {
        localVideoRef.current.srcObject = stream;
      }
    };

    // STT 결과 핸들러
    client.onTranscript = (data) => {
      console.log('📥 onTranscript received:', data);
      const { text, source, timestamp, is_final } = data;
      const receiveTime = Date.now();
      const latency = timestamp ? receiveTime - (timestamp * 1000) : 0;

      console.log(`📝 Processing ${source} result (is_final=${is_final}):`, text);

      if (source === 'google') {
        if (is_final) {
          // Final 결과: partial 비우고 결과 리스트에 추가
          setGooglePartial('');
          const result = {
            id: `${source}-${receiveTime}`,
            text,
            timestamp: receiveTime,
            latency: Math.max(0, latency),
            source
          };
          setGoogleResults(prev => [...prev.slice(-49), result]);
          setStats(prev => {
            const newCount = prev.google.count + 1;
            const newTotalLatency = prev.google.totalLatency + latency;
            return {
              ...prev,
              google: {
                count: newCount,
                totalLatency: newTotalLatency,
                avgLatency: newTotalLatency / newCount
              }
            };
          });
        } else {
          // Partial 결과: 실시간 표시 영역에 교체
          setGooglePartial(text);
        }
      } else if (source === 'elevenlabs') {
        if (is_final) {
          // Final 결과: partial 비우고 결과 리스트에 추가
          setElevenlabsPartial('');
          const result = {
            id: `${source}-${receiveTime}`,
            text,
            timestamp: receiveTime,
            latency: Math.max(0, latency),
            source
          };
          setElevenlabsResults(prev => [...prev.slice(-49), result]);
          setStats(prev => {
            const newCount = prev.elevenlabs.count + 1;
            const newTotalLatency = prev.elevenlabs.totalLatency + latency;
            return {
              ...prev,
              elevenlabs: {
                count: newCount,
                totalLatency: newTotalLatency,
                avgLatency: newTotalLatency / newCount
              }
            };
          });
        } else {
          // Partial 결과: 실시간 표시 영역에 교체
          setElevenlabsPartial(text);
        }
      }
    };

    // Dual STT 상태 핸들러
    client.onDualSttStatus = (data) => {
      console.log('Dual STT status:', data);
      setDualSttEnabled(data.enabled);
    };

    return () => {
      if (clientRef.current) {
        clientRef.current.disconnect();
      }
    };
  }, []);

  // 연결/연결 해제
  const handleConnect = useCallback(async () => {
    if (isConnected) {
      clientRef.current?.disconnect();
      setIsConnected(false);
      setIsRecording(false);
      setDualSttEnabled(false);
      setConnectionStatus('disconnected');
    } else {
      try {
        setConnectionStatus('connecting');
        // 1. WebSocket 연결
        await clientRef.current?.connect();
        // 2. STT 비교용 임시 방 입장
        await clientRef.current?.joinRoom('stt-comparison-room', 'STT-Tester');
        setIsConnected(true);
        setConnectionStatus('connected');
      } catch (error) {
        console.error('Connection failed:', error);
        setConnectionStatus('failed');
      }
    }
  }, [isConnected]);

  // 녹음 시작/중지
  const handleRecording = useCallback(async () => {
    if (!isConnected) return;

    if (isRecording) {
      // 녹음 중지
      clientRef.current?.stopCall();
      setIsRecording(false);
    } else {
      // 녹음 시작 - startCall로 미디어 획득 + WebRTC 연결 생성
      try {
        await clientRef.current?.startCall();
        setIsRecording(true);
      } catch (error) {
        console.error('Failed to start recording:', error);
      }
    }
  }, [isConnected, isRecording]);

  // 듀얼 STT 토글
  const handleToggleDualStt = useCallback(() => {
    if (!isConnected) return;

    const newEnabled = !dualSttEnabled;
    clientRef.current?.sendMessage({
      type: 'enable_dual_stt',
      data: { enabled: newEnabled }
    });
  }, [isConnected, dualSttEnabled]);

  // 결과 초기화
  const handleClearResults = useCallback(() => {
    setGoogleResults([]);
    setElevenlabsResults([]);
    setGooglePartial('');
    setElevenlabsPartial('');
    setStats({
      google: { count: 0, avgLatency: 0, totalLatency: 0 },
      elevenlabs: { count: 0, avgLatency: 0, totalLatency: 0 }
    });
  }, []);

  // 시간 포맷
  const formatTime = (timestamp) => {
    const date = new Date(timestamp);
    return date.toLocaleTimeString('ko-KR', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      fractionalSecondDigits: 1
    });
  };

  return (
    <div className="stt-comparison">
      {/* Header */}
      <header className="comparison-header">
        <div className="header-left">
          <Link to="/" className="back-link">← 메인으로</Link>
          <h1>STT 엔진 비교</h1>
        </div>
        <div className="header-right">
          <span className={`status-badge ${connectionStatus}`}>
            {connectionStatus === 'connected' ? '연결됨' :
             connectionStatus === 'connecting' ? '연결 중...' :
             connectionStatus === 'failed' ? '연결 실패' : '연결 안됨'}
          </span>
        </div>
      </header>

      {/* Controls */}
      <div className="controls-panel">
        <div className="control-group">
          <button
            className={`control-btn ${isConnected ? 'disconnect' : 'connect'}`}
            onClick={handleConnect}
          >
            {isConnected ? '연결 해제' : '서버 연결'}
          </button>

          <button
            className={`control-btn ${isRecording ? 'stop' : 'record'}`}
            onClick={handleRecording}
            disabled={!isConnected}
          >
            {isRecording ? '녹음 중지' : '녹음 시작'}
          </button>

          <button
            className={`control-btn toggle ${dualSttEnabled ? 'active' : ''}`}
            onClick={handleToggleDualStt}
            disabled={!isConnected}
          >
            {dualSttEnabled ? 'ElevenLabs ON' : 'ElevenLabs OFF'}
          </button>

          <button
            className="control-btn clear"
            onClick={handleClearResults}
          >
            결과 초기화
          </button>
        </div>

        {/* Audio Preview */}
        <div className="audio-preview">
          <video
            ref={localVideoRef}
            autoPlay
            muted
            playsInline
            style={{ display: 'none' }}
          />
          {isRecording && (
            <div className="recording-indicator">
              <span className="pulse"></span>
              녹음 중...
            </div>
          )}
        </div>
      </div>

      {/* Stats Panel */}
      <div className="stats-panel">
        <div className="stat-card google">
          <h3>Google Cloud STT</h3>
          <div className="stat-row">
            <span>인식 횟수:</span>
            <strong>{stats.google.count}</strong>
          </div>
          <div className="stat-row">
            <span>평균 지연:</span>
            <strong>{stats.google.avgLatency.toFixed(0)}ms</strong>
          </div>
        </div>

        <div className="stat-card elevenlabs">
          <h3>ElevenLabs STT</h3>
          <div className="stat-row">
            <span>인식 횟수:</span>
            <strong>{stats.elevenlabs.count}</strong>
          </div>
          <div className="stat-row">
            <span>평균 지연:</span>
            <strong>{stats.elevenlabs.avgLatency.toFixed(0)}ms</strong>
          </div>
          {!dualSttEnabled && (
            <div className="disabled-notice">비활성화됨</div>
          )}
        </div>
      </div>

      {/* Results Comparison */}
      <div className="results-comparison">
        {/* Google Results */}
        <div className="result-panel google">
          <div className="panel-header">
            <h2>Google Cloud STT</h2>
            <span className="result-count">{googleResults.length} 결과</span>
          </div>

          {/* 현재 인식 중 영역 */}
          {googlePartial && (
            <div className="partial-result">
              <span className="partial-label">🎤 인식 중...</span>
              <span className="partial-text">{googlePartial}</span>
            </div>
          )}

          <div className="result-list" ref={googleResultsRef}>
            {googleResults.length === 0 && !googlePartial ? (
              <div className="empty-state">
                녹음을 시작하면 결과가 표시됩니다.
              </div>
            ) : (
              googleResults.map(result => (
                <div key={result.id} className="result-item">
                  <div className="result-meta">
                    <span className="result-time">{formatTime(result.timestamp)}</span>
                    <span className="result-latency">{result.latency.toFixed(0)}ms</span>
                  </div>
                  <div className="result-text">{result.text}</div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* ElevenLabs Results */}
        <div className={`result-panel elevenlabs ${!dualSttEnabled ? 'disabled' : ''}`}>
          <div className="panel-header">
            <h2>ElevenLabs STT</h2>
            <span className="result-count">{elevenlabsResults.length} 결과</span>
          </div>

          {/* 현재 인식 중 영역 */}
          {dualSttEnabled && elevenlabsPartial && (
            <div className="partial-result">
              <span className="partial-label">🎤 인식 중...</span>
              <span className="partial-text">{elevenlabsPartial}</span>
            </div>
          )}

          <div className="result-list" ref={elevenlabsResultsRef}>
            {!dualSttEnabled ? (
              <div className="empty-state">
                ElevenLabs STT를 활성화하세요.
              </div>
            ) : elevenlabsResults.length === 0 && !elevenlabsPartial ? (
              <div className="empty-state">
                녹음을 시작하면 결과가 표시됩니다.
              </div>
            ) : (
              elevenlabsResults.map(result => (
                <div key={result.id} className="result-item">
                  <div className="result-meta">
                    <span className="result-time">{formatTime(result.timestamp)}</span>
                    <span className="result-latency">{result.latency.toFixed(0)}ms</span>
                  </div>
                  <div className="result-text">{result.text}</div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      {/* Info Panel */}
      <div className="info-panel">
        <h3>사용 방법</h3>
        <ol>
          <li>서버 연결 버튼을 클릭하여 WebRTC 연결을 시작합니다.</li>
          <li>ElevenLabs 버튼을 클릭하여 듀얼 STT 모드를 활성화합니다.</li>
          <li>녹음 시작 버튼을 클릭하고 말하면 두 엔진의 결과가 실시간으로 표시됩니다.</li>
          <li>평균 지연 시간과 인식 결과를 비교해보세요.</li>
        </ol>
        <p className="note">
          <strong>참고:</strong> ElevenLabs STT를 사용하려면 백엔드에 ELEVENLABS_API_KEY가 설정되어 있어야 합니다.
        </p>
      </div>
    </div>
  );
}

export default STTComparison;
