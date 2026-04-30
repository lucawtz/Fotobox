import { ReactNode } from "react";
import { Paper, Box, Typography, Stack } from "@mui/material";

interface Props {
  title: string;
  description?: string;
  icon?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
}

export default function SettingsCard({ title, description, icon, children, footer }: Props) {
  return (
    <Paper
      elevation={0}
      sx={{
        borderRadius: 3,
        border: "1px solid",
        borderColor: "divider",
        overflow: "hidden",
      }}
    >
      <Box sx={{ p: { xs: 2.25, sm: 3 } }}>
        <Stack direction="row" spacing={2} alignItems="flex-start" sx={{ mb: description ? 0.5 : 0 }}>
          {icon && (
            <Box
              sx={{
                width: 40, height: 40, borderRadius: 2,
                display: "grid", placeItems: "center",
                bgcolor: "#e8f0fe",
                color: "primary.main",
                flexShrink: 0,
              }}
            >
              {icon}
            </Box>
          )}
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Typography variant="h6" sx={{ fontWeight: 600, fontSize: "1.05rem" }}>
              {title}
            </Typography>
            {description && (
              <Typography variant="body2" color="text.secondary" sx={{ mt: 0.25 }}>
                {description}
              </Typography>
            )}
          </Box>
        </Stack>
        <Box sx={{ mt: 2.5 }}>{children}</Box>
      </Box>
      {footer && (
        <Box
          sx={{
            px: { xs: 2.25, sm: 3 },
            py: 1.5,
            bgcolor: "grey.50",
            borderTop: "1px solid",
            borderColor: "divider",
            display: "flex",
            justifyContent: "flex-end",
            gap: 1,
          }}
        >
          {footer}
        </Box>
      )}
    </Paper>
  );
}
