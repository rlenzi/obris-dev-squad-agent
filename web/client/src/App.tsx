import type { ReactNode } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { useAuth } from '@/lib/auth';
import Layout from '@/components/Layout';
import LoginPage from '@/pages/Login';
import ClientDashboardPage from '@/pages/Dashboard';
import SquadsListPage from '@/pages/Squads';
import SquadDetailPage from '@/pages/SquadDetail';
import SquadKnowledgePage from '@/pages/SquadKnowledge';
import AgentDetailPage from '@/pages/AgentDetail';
import AgentRunDetailPage from '@/pages/AgentRunDetail';
import CredentialsPage from '@/pages/Credentials';
import CostPage from '@/pages/Cost';
import SetupPage from '@/pages/Setup';
import SetupChoicePage from '@/pages/SetupChoice';
import SetupGreenfieldPlaceholderPage from '@/pages/SetupGreenfieldPlaceholder';
import SetupExplorePlaceholderPage from '@/pages/SetupExplorePlaceholder';
import SetupRepositoryPage from '@/pages/SetupRepository';
import SetupAnalyzingPlaceholderPage from '@/pages/SetupAnalyzingPlaceholder';
import ComingSoonPage from '@/pages/ComingSoon';
import { fetchSquadsForClient } from '@/lib/api';
import { useClientId } from '@/lib/use-client-id';

function CredentialsWithClient() {
  const clientId = useClientId();
  return <CredentialsPage clientId={clientId} />;
}

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
  return <>{children}</>;
}

/**
 * Envolve as rotas que precisam do tenant configurado. Se squad_count == 0,
 * redireciona pra /setup. Senão renderiza dentro do Layout.
 */
function RequireSetupComplete({ children }: { children: ReactNode }) {
  const clientId = useClientId();
  const squadsQuery = useQuery({
    queryKey: ['squads', clientId],
    queryFn: () => fetchSquadsForClient(clientId),
    enabled: Boolean(clientId),
  });

  if (squadsQuery.isLoading) {
    return (
      <div className="min-h-screen grid place-items-center text-muted-foreground">
        Carregando tenant…
      </div>
    );
  }
  if ((squadsQuery.data ?? []).length === 0) {
    return <Navigate to="/setup" replace />;
  }
  return <Layout>{children}</Layout>;
}

/**
 * Para a tela /setup: exige auth mas NÃO exige squad existente.
 * Se já tem squad, redireciona pro dashboard pra evitar reentrar no wizard.
 */
function SetupGate({ children }: { children: ReactNode }) {
  const clientId = useClientId();
  const squadsQuery = useQuery({
    queryKey: ['squads', clientId],
    queryFn: () => fetchSquadsForClient(clientId),
    enabled: Boolean(clientId),
  });

  if (squadsQuery.isLoading) {
    return (
      <div className="min-h-screen grid place-items-center text-muted-foreground">
        Carregando tenant…
      </div>
    );
  }
  if ((squadsQuery.data ?? []).length > 0) {
    return <Navigate to="/dashboard" replace />;
  }
  return (
    <div className="min-h-screen bg-background px-4 py-10">{children}</div>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        path="/setup"
        element={
          <ProtectedRoute>
            <SetupGate>
              <SetupPage />
            </SetupGate>
          </ProtectedRoute>
        }
      />
      {/* Redesign do onboarding (PR-4 de 8) — tela 0 acessivel direto.
          O switch final do /setup pra tela 0 acontece no PR-8. */}
      <Route
        path="/setup/start"
        element={
          <ProtectedRoute>
            <SetupGate>
              <div className="min-h-screen bg-background">
                <SetupChoicePage />
              </div>
            </SetupGate>
          </ProtectedRoute>
        }
      />
      <Route
        path="/setup/greenfield"
        element={
          <ProtectedRoute>
            <SetupGate>
              <div className="min-h-screen bg-background">
                <SetupGreenfieldPlaceholderPage />
              </div>
            </SetupGate>
          </ProtectedRoute>
        }
      />
      <Route
        path="/setup/explore"
        element={
          <ProtectedRoute>
            <SetupGate>
              <div className="min-h-screen bg-background">
                <SetupExplorePlaceholderPage />
              </div>
            </SetupGate>
          </ProtectedRoute>
        }
      />
      {/* PR-5 do redesign — Tela 1 */}
      <Route
        path="/setup/repository"
        element={
          <ProtectedRoute>
            <SetupGate>
              <div className="min-h-screen bg-background">
                <SetupRepositoryPage />
              </div>
            </SetupGate>
          </ProtectedRoute>
        }
      />
      {/* Placeholder Tela 2 (PR-6 implementa) — fora do SetupGate porque
          ja existe squad e o gate redirecionaria pra /dashboard */}
      <Route
        path="/setup/analyzing/:squadId"
        element={
          <ProtectedRoute>
            <div className="min-h-screen bg-background">
              <SetupAnalyzingPlaceholderPage />
            </div>
          </ProtectedRoute>
        }
      />
      <Route
        path="/dashboard"
        element={
          <ProtectedRoute>
            <RequireSetupComplete>
              <ClientDashboardPage />
            </RequireSetupComplete>
          </ProtectedRoute>
        }
      />
      <Route
        path="/squads"
        element={
          <ProtectedRoute>
            <RequireSetupComplete>
              <SquadsListPage />
            </RequireSetupComplete>
          </ProtectedRoute>
        }
      />
      <Route
        path="/squads/:squadId/agents/:agentId/runs/:taskId"
        element={
          <ProtectedRoute>
            <RequireSetupComplete>
              <AgentRunDetailPage />
            </RequireSetupComplete>
          </ProtectedRoute>
        }
      />
      <Route
        path="/squads/:squadId/agents/:agentId"
        element={
          <ProtectedRoute>
            <RequireSetupComplete>
              <AgentDetailPage />
            </RequireSetupComplete>
          </ProtectedRoute>
        }
      />
      <Route
        path="/squads/:squadId"
        element={
          <ProtectedRoute>
            <RequireSetupComplete>
              <SquadDetailPage />
            </RequireSetupComplete>
          </ProtectedRoute>
        }
      />
      <Route
        path="/squads/:squadId/knowledge"
        element={
          <ProtectedRoute>
            <RequireSetupComplete>
              <SquadKnowledgePage />
            </RequireSetupComplete>
          </ProtectedRoute>
        }
      />
      <Route
        path="/agents"
        element={
          <ProtectedRoute>
            <RequireSetupComplete>
              <ComingSoonPage
                title="Agentes (cross-squad)"
                description="Visão consolidada de todos os agentes do tenant em todas as squads. Em construção."
              />
            </RequireSetupComplete>
          </ProtectedRoute>
        }
      />
      <Route
        path="/cost"
        element={
          <ProtectedRoute>
            <RequireSetupComplete>
              <CostPage />
            </RequireSetupComplete>
          </ProtectedRoute>
        }
      />
      <Route
        path="/credentials"
        element={
          <ProtectedRoute>
            <RequireSetupComplete>
              <CredentialsWithClient />
            </RequireSetupComplete>
          </ProtectedRoute>
        }
      />
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  );
}
