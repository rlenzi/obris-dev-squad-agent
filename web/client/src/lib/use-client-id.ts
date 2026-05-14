import { useAuth } from './auth';

/**
 * Retorna o client_id do tenant atual a partir do user logado.
 *
 * No painel cliente, o user pertence a UM tenant (membership). Esse hook
 * facilita o acesso evitando ter clientId nas URLs (vs admin que usa
 * /clients/:clientId/... porque admin navega entre tenants).
 *
 * Lança erro se chamado sem auth completa.
 */
export function useClientId(): string {
  const { me } = useAuth();
  const clientId = me?.memberships?.[0]?.client_id;
  if (!clientId) {
    throw new Error(
      'useClientId chamado sem auth completa — verifique ProtectedRoute',
    );
  }
  return clientId;
}
