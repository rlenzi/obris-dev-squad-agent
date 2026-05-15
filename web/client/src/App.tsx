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
import SetupChoicePage from '@/pages/SetupChoice';
import SetupGreenfieldPlaceholderPage from '@/pages/SetupGreenfieldPlaceholder';
import SetupExplorePage from '@/pages/SetupExplore';
import SetupRepositoryPage from '@/pages/SetupRepository';
import SetupAnalyzingPage from '@/pages/SetupAnalyzing';
import SetupResultPage from '@/pages/SetupResult';
import SetupReadyPage from '@/pages/SetupReady';
import TasksListPage from '@/pages/TasksList';
import TaskDetailPage from '@/pages/TaskDetail';
import DemandsPage from '@/pages/Demands';
import SettingsPage from '@/pages/Settings';
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

  // S-5: ?new=1 permite acessar /setup mesmo com squad existente
  // (fluxo "criar 2ª/3ª squad")
  const allowNew = new URLSearchParams(window.location.search).has('new');

  if (squadsQuery.isLoading) {
    return (
      <div className="min-h-screen grid place-items-center text-muted-foreground">
        Carregando tenant…
      </div>
    );
  }
  if ((squadsQuery.data ?? []).length > 0 && !allowNew) {
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
      {/* /setup eh a porta de entrada do redesign (PR-8 switch final).
          Wizard antigo foi removido. /setup/start mantido como alias. */}
      <Route
        path="/setup"
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
        path="/setup/start"
        element={<Navigate to="/setup" replace />}
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
                <SetupExplorePage />
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
              <SetupAnalyzingPage />
            </div>
          </ProtectedRoute>
        }
      />
      {/* PR-7 do redesign — Tela 3 (resultado + agentes) */}
      <Route
        path="/setup/result/:squadId"
        element={
          <ProtectedRoute>
            <div className="min-h-screen bg-background">
              <SetupResultPage />
            </div>
          </ProtectedRoute>
        }
      />
      {/* Tela 4 (squad ativa) — destino do botão Ativar. */}
      <Route
        path="/setup/ready/:squadId"
        element={
          <ProtectedRoute>
            <div className="min-h-screen bg-background">
              <SetupReadyPage />
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
      {/* S-2 do redesign — Tasks tenant-wide */}
      <Route
        path="/tasks"
        element={
          <ProtectedRoute>
            <RequireSetupComplete>
              <TasksListPage />
            </RequireSetupComplete>
          </ProtectedRoute>
        }
      />
      <Route
        path="/tasks/:taskId"
        element={
          <ProtectedRoute>
            <RequireSetupComplete>
              <TaskDetailPage />
            </RequireSetupComplete>
          </ProtectedRoute>
        }
      />
      {/* S-7 do redesign — Demandas (mini-Jira embutido) */}
      <Route
        path="/demands"
        element={
          <ProtectedRoute>
            <RequireSetupComplete>
              <DemandsPage />
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
      {/* S-8 do redesign — Configuracoes do tenant */}
      <Route
        path="/settings"
        element={
          <ProtectedRoute>
            <RequireSetupComplete>
              <SettingsPage />
            </RequireSetupComplete>
          </ProtectedRoute>
        }
      />
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  );
}
