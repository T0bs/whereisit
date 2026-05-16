// TanStack Query hooks. Pure thin wrappers over `api` — keep query keys
// stable and invalidate after mutations.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./api";

export const qk = {
  rootNodes: ["nodes", "root"],
  children: (id) => ["nodes", "children", id],
  node: (id) => ["nodes", id],
  path: (id) => ["nodes", "path", id],
  kinds: ["kinds"],
  tags: ["tags"],
  search: (params) => ["search", params],
  embeddingsStatus: ["embeddings", "status"],
  bulkState: ["bulk", "state"],
};

export function useRootNodes() {
  return useQuery({ queryKey: qk.rootNodes, queryFn: api.listRootNodes });
}

export function useChildren(id) {
  return useQuery({
    queryKey: qk.children(id),
    queryFn: () => api.getChildren(id),
    enabled: id != null,
  });
}

export function useNode(id) {
  return useQuery({
    queryKey: qk.node(id),
    queryFn: () => api.getNode(id),
    enabled: id != null,
  });
}

export function useKinds() {
  return useQuery({ queryKey: qk.kinds, queryFn: api.listKinds, staleTime: 5 * 60_000 });
}

export function useSearch(params, opts = {}) {
  return useQuery({
    queryKey: qk.search(params),
    queryFn: () => api.search(params),
    enabled: !!params?.q && (opts.enabled ?? true),
  });
}

export function useEmbeddingsStatus() {
  return useQuery({ queryKey: qk.embeddingsStatus, queryFn: api.embeddingsStatus });
}

function invalidateNodeTree(queryClient) {
  queryClient.invalidateQueries({ queryKey: ["nodes"] });
  queryClient.invalidateQueries({ queryKey: ["search"] });
}

export function useCreateNode() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: api.createNode,
    onSuccess: () => invalidateNodeTree(queryClient),
  });
}

export function useUpdateNode() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }) => api.updateNode(id, body),
    onSuccess: () => invalidateNodeTree(queryClient),
  });
}

export function useDeleteNode() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, cascade }) => api.deleteNode(id, cascade),
    onSuccess: () => invalidateNodeTree(queryClient),
  });
}

export function useAddTag() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ nodeId, name }) => api.addTag(nodeId, name),
    onSuccess: (_data, vars) => {
      queryClient.invalidateQueries({ queryKey: qk.node(vars.nodeId) });
      queryClient.invalidateQueries({ queryKey: qk.tags });
    },
  });
}

export function useRemoveTag() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ nodeId, tagId }) => api.removeTag(nodeId, tagId),
    onSuccess: (_data, vars) => {
      queryClient.invalidateQueries({ queryKey: qk.node(vars.nodeId) });
    },
  });
}

export function useAsk() {
  return useMutation({ mutationFn: api.ask });
}

export function useBackfillEmbeddings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: api.backfillEmbeddings,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: qk.embeddingsStatus }),
  });
}

// M13 — bulk + categories

export function useBulkState() {
  return useQuery({ queryKey: qk.bulkState, queryFn: api.bulkState });
}

function invalidateBulk(queryClient) {
  queryClient.invalidateQueries({ queryKey: qk.bulkState });
  queryClient.invalidateQueries({ queryKey: ["nodes"] });
  queryClient.invalidateQueries({ queryKey: ["search"] });
}

export function useBulkAdd() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (names) => api.bulkAdd(names),
    onSuccess: () => invalidateBulk(queryClient),
  });
}

export function useSuggestCategories() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: api.suggestCategories,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: qk.bulkState }),
  });
}

export function useAcceptCategories() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: api.acceptCategories,
    onSuccess: () => invalidateBulk(queryClient),
  });
}
