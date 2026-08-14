import { exposeUserFacingRoles } from "../runtime/role-access.js"


export const BiexceRoleAccessPlugin = async ({ client }) => ({
  config: async (config) => {
    const result = exposeUserFacingRoles(config)
    if (result.ok) return
    try {
      await client.app.log({
        body: {
          service: "biexce-role-access",
          level: "warn",
          message: "BIEXCE roles were not fully registered by Slim",
          extra: { missing: result.missing },
        },
      })
    } catch {
      // Missing diagnostics must not make OpenCode startup fail.
    }
  },
})
