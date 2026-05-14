import type { ReactNode } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import { useAuth } from '@/lib/auth';
import Layout from '@/components/Layout';
import LoginPage from '@/pages/Login';
import ClientDashboardPage from '@/pages/Dashboard';
import SquadsListPage from '@/pages/Squads';
import SquadDetailPage from '@/pages/SquadDetail';
import AgentDetailPage from '@/pages/AgentDetail';
import AgentRunDetailPage from '@/pages/AgentRunDetail';
import CredentialsPage from '@/pages/Credentials';
import ComingSoonPage from '@/pages/ComingSoon';

function ProtectedRoute({ children }: { children: ReactNode }) {
  const { isAuthenticated, isLoading } = useAuth();
  if (isLoading) {
    return (
      <div className="min-h-screen grid place-items-center text-muted-foreground">
        Carregando…
      </div>
    );
  }
  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }
  return <Layout>{children}</Layout>;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        path="/dashboard"
        element={
          <ProtectedRoute>
            <ClientDashboardPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/squads"
        element={
          <ProtectedRoute>
            <SquadsListPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/squads/:squadId/agents/:agentId/runs/:taskId"
        element={
          <ProtectedRoute>
            <AgentRunDetailPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/squads/:squadId/agents/:agentId"
        element={
          <ProtectedRoute>
            <AgentDetailPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/squads/:squadId"
        element={
          <ProtectedRoute>
            <SquadDetailPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/agents"
        element={
          <ProtectedRoute>
            <ComingSoonPage
              title="Agentes (cross-squad)"
              description="Visão consolidada de todos os agentes do tenant em todas as squads. Em construção."
            />
          </ProtectedRoute>
        }
      />
      <Route
        path="/cost"
        element={
          <ProtectedRoute>
            <ComingSoonPage
              title="Custos"
              description="Consumo do mês corrente + faturável. Em construção."
            />
          </ProtectedRoute>
        }
      />
      <Route
        path="/credentials"
        element={
          <ProtectedRoute>
            <CredentialsPage />
          </ProtectedRoute>
        }
      />
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  );
}
