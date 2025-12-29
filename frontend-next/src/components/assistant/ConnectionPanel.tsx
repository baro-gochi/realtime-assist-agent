"use client";

/**
 * ConnectionPanel - WebRTC 연결 및 룸 관리 UI
 */

import { useState } from 'react';
import type { RoomInfo, UserRole } from '@/lib/types';

interface ConnectionPanelProps {
  userRole: UserRole;
  isConnected: boolean;
  isInRoom: boolean;
  error: string;
  onConnect: () => Promise<void>;
  onJoinRoom: (roomName: string, nickname: string, phoneNumber?: string, agentCode?: string) => Promise<void>;
  onResetRole: () => void;
}

export function ConnectionPanel({
  userRole,
  isConnected,
  isInRoom,
  error,
  onConnect,
  onJoinRoom,
  onResetRole,
}: ConnectionPanelProps) {
  const [roomInput, setRoomInput] = useState('');
  const [nicknameInput, setNicknameInput] = useState('');
  const [phoneInput, setPhoneInput] = useState('');
  const [agentCodeInput, setAgentCodeInput] = useState('');
  const [availableRooms, setAvailableRooms] = useState<RoomInfo[]>([]);
  const [loadingRooms, setLoadingRooms] = useState(false);
  const [localError, setLocalError] = useState('');

  const fetchRooms = async () => {
    const apiBase = process.env.NEXT_PUBLIC_API_URL || '';
    const apiUrl = `${apiBase}/api/rooms`;

    setLoadingRooms(true);
    setLocalError('');
    try {
      const headers: HeadersInit = {
        'bypass-tunnel-reminder': 'true',
        'ngrok-skip-browser-warning': 'true',
      };
      const authToken = sessionStorage.getItem('auth_token');
      if (authToken) {
        headers['Authorization'] = `Bearer ${authToken}`;
      }

      const response = await fetch(apiUrl, { headers });
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      setAvailableRooms(data.rooms || []);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setLocalError(`Failed to fetch rooms: ${message}`);
    } finally {
      setLoadingRooms(false);
    }
  };

  const handleCreateRoomAsAgent = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!roomInput.trim() || !nicknameInput.trim()) {
      setLocalError('Room name and nickname required');
      return;
    }
    setLocalError('');
    await onJoinRoom(roomInput.trim(), nicknameInput.trim(), undefined, agentCodeInput.trim());
  };

  const handleJoinRoomAsCustomer = async (room: RoomInfo) => {
    if (!nicknameInput.trim()) {
      setLocalError('Name is required');
      return;
    }
    if (!phoneInput.trim()) {
      setLocalError('Phone number is required');
      return;
    }
    setLocalError('');
    await onJoinRoom(room.room_name, nicknameInput.trim(), phoneInput.trim());
  };

  // Server connection step
  if (!isConnected) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-bg-primary p-6">
        <div className="w-full max-w-md rounded-xl border border-border-primary bg-bg-card p-8 shadow-lg">
          <h2 className="mb-2 text-center text-xl font-bold text-text-primary">
            {userRole === 'agent' ? 'Agent Connection' : 'Customer Connection'}
          </h2>
          <p className="mb-6 text-center text-sm text-text-secondary">
            Connect to server to start
          </p>
          <button
            onClick={onConnect}
            className="w-full rounded-lg bg-primary px-4 py-3 font-medium text-white transition-colors hover:bg-primary/90"
          >
            Connect to Server
          </button>
          {(error || localError) && (
            <div className="mt-4 rounded-lg bg-status-error/10 p-3 text-sm text-status-error">
              {error || localError}
            </div>
          )}
          <button
            onClick={onResetRole}
            className="mt-4 w-full rounded-lg border border-border-primary bg-bg-secondary px-4 py-2 text-sm text-text-secondary transition-colors hover:bg-bg-secondary/80"
          >
            Select Role Again
          </button>
        </div>
      </div>
    );
  }

  // Room creation (Agent)
  if (!isInRoom && userRole === 'agent') {
    return (
      <div className="flex min-h-screen items-center justify-center bg-bg-primary p-6">
        <div className="w-full max-w-md rounded-xl border border-border-primary bg-bg-card p-8 shadow-lg">
          <h2 className="mb-6 text-center text-xl font-bold text-text-primary">
            Create Consultation Room
          </h2>
          <form onSubmit={handleCreateRoomAsAgent} className="space-y-4">
            <div>
              <label className="mb-1 block text-sm font-medium text-text-secondary">
                Room Name
              </label>
              <input
                type="text"
                placeholder="e.g., Room 1"
                value={roomInput}
                onChange={(e) => setRoomInput(e.target.value)}
                className="w-full rounded-lg border border-border-primary bg-bg-input px-4 py-2 text-text-primary placeholder:text-text-muted focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
                autoFocus
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-text-secondary">
                Agent Name
              </label>
              <input
                type="text"
                placeholder="Enter your name"
                value={nicknameInput}
                onChange={(e) => setNicknameInput(e.target.value)}
                className="w-full rounded-lg border border-border-primary bg-bg-input px-4 py-2 text-text-primary placeholder:text-text-muted focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-text-secondary">
                Agent Code
              </label>
              <input
                type="text"
                placeholder="e.g., A001"
                value={agentCodeInput}
                onChange={(e) => setAgentCodeInput(e.target.value)}
                className="w-full rounded-lg border border-border-primary bg-bg-input px-4 py-2 text-text-primary placeholder:text-text-muted focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
              />
            </div>
            <button
              type="submit"
              className="w-full rounded-lg bg-accent-green px-4 py-3 font-medium text-white transition-colors hover:bg-accent-green/90"
            >
              Create Room
            </button>
          </form>
          {(error || localError) && (
            <div className="mt-4 rounded-lg bg-status-error/10 p-3 text-sm text-status-error">
              {error || localError}
            </div>
          )}
        </div>
      </div>
    );
  }

  // Room selection (Customer)
  if (!isInRoom && userRole === 'customer') {
    return (
      <div className="flex min-h-screen items-center justify-center bg-bg-primary p-6">
        <div className="w-full max-w-2xl rounded-xl border border-border-primary bg-bg-card p-8 shadow-lg">
          <h2 className="mb-6 text-center text-xl font-bold text-text-primary">
            Available Consultation Rooms
          </h2>

          <div className="mb-4 space-y-4">
            <div>
              <label className="mb-1 block text-sm font-medium text-text-secondary">
                Customer Name
              </label>
              <input
                type="text"
                placeholder="Enter your name"
                value={nicknameInput}
                onChange={(e) => setNicknameInput(e.target.value)}
                className="w-full rounded-lg border border-border-primary bg-bg-input px-4 py-2 text-text-primary placeholder:text-text-muted focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-text-secondary">
                Phone Number
              </label>
              <input
                type="tel"
                placeholder="010-1234-5678"
                value={phoneInput}
                onChange={(e) => setPhoneInput(e.target.value)}
                className="w-full rounded-lg border border-border-primary bg-bg-input px-4 py-2 text-text-primary placeholder:text-text-muted focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
              />
            </div>
          </div>

          <button
            onClick={fetchRooms}
            disabled={loadingRooms}
            className="mb-6 w-full rounded-lg bg-primary px-4 py-2 font-medium text-white transition-colors hover:bg-primary/90 disabled:opacity-50"
          >
            {loadingRooms ? 'Loading...' : 'Refresh Room List'}
          </button>

          {availableRooms.length === 0 ? (
            <p className="text-center text-text-muted">
              No available rooms at the moment.
            </p>
          ) : (
            <div className="grid gap-4 sm:grid-cols-2">
              {availableRooms.map((room, index) => (
                <button
                  key={index}
                  onClick={() => handleJoinRoomAsCustomer(room)}
                  className="rounded-lg border border-border-primary bg-bg-secondary p-4 text-left transition-colors hover:border-primary hover:bg-primary/5"
                >
                  <div className="flex items-center justify-between">
                    <h3 className="font-semibold text-text-primary">{room.room_name}</h3>
                    <span className="rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">
                      {room.peer_count} users
                    </span>
                  </div>
                  <div className="mt-2 text-sm text-text-secondary">
                    Agent: {room.peers?.[0]?.nickname || 'Unknown'}
                  </div>
                  <div className="mt-1 flex items-center gap-1">
                    <span className="h-2 w-2 rounded-full bg-accent-green"></span>
                    <span className="text-xs text-accent-green">Waiting</span>
                  </div>
                </button>
              ))}
            </div>
          )}

          {(error || localError) && (
            <div className="mt-4 rounded-lg bg-status-error/10 p-3 text-sm text-status-error">
              {error || localError}
            </div>
          )}
        </div>
      </div>
    );
  }

  return null;
}
