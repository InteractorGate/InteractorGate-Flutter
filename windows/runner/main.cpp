#include <flutter/dart_project.h>
#include <flutter/flutter_view_controller.h>
#include <windows.h>

#include "flutter_window.h"
#include "utils.h"

// Mete este proceso en un Job Object con KILL_ON_JOB_CLOSE. Los procesos hijo
// (el sidecar de mirada gaze_service.exe / python.exe) heredan el job, asi que
// cuando la app termina -cerrando la ventana, por un fallo o matada desde el
// Administrador de tareas- Windows cierra el ultimo handle del job y mata a
// todos los hijos. Sin esto el sidecar quedaba huerfano moviendo el cursor con
// la mirada. El handle se deja abierto a proposito: vive lo que vive el proceso.
static void KillChildrenOnExit() {
  HANDLE job = ::CreateJobObjectW(nullptr, nullptr);
  if (job == nullptr) return;
  JOBOBJECT_EXTENDED_LIMIT_INFORMATION info = {};
  info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
  if (!::SetInformationJobObject(job, JobObjectExtendedLimitInformation, &info,
                                 sizeof(info)) ||
      !::AssignProcessToJobObject(job, ::GetCurrentProcess())) {
    // Sin job queda la segunda red: el sidecar vigila el PID de la app.
    ::CloseHandle(job);
  }
}

int APIENTRY wWinMain(_In_ HINSTANCE instance, _In_opt_ HINSTANCE prev,
                      _In_ wchar_t *command_line, _In_ int show_command) {
  KillChildrenOnExit();

  // Attach to console when present (e.g., 'flutter run') or create a
  // new console when running with a debugger.
  if (!::AttachConsole(ATTACH_PARENT_PROCESS) && ::IsDebuggerPresent()) {
    CreateAndAttachConsole();
  }

  // Initialize COM, so that it is available for use in the library and/or
  // plugins.
  ::CoInitializeEx(nullptr, COINIT_APARTMENTTHREADED);

  flutter::DartProject project(L"data");

  std::vector<std::string> command_line_arguments =
      GetCommandLineArguments();

  project.set_dart_entrypoint_arguments(std::move(command_line_arguments));

  FlutterWindow window(project);
  // Ventana reducida y CENTRADA en las dos direcciones dentro del area de
  // trabajo (asi no queda detras de la barra de tareas).
  //
  // Estuvo pegada al borde inferior hasta el 2026-09-09. El problema no era
  // estetico: con la ventana abajo, el tablero vivia en el 63-94 % de la altura
  // de la pantalla, o sea unos 27 grados por debajo de la linea de los ojos.
  // Mirar tan abajo hace que el parpado tape parte del iris justo cuando hay
  // que estimar la mirada, y ademas obligaba a calibrar hasta el 97 % de la
  // altura, al borde mismo de la pantalla. Fue el problema de fondo del eje
  // vertical de toda la jornada del 06/09.
  //
  // IMPORTANTE: sidecar/geometria.py deduce donde esta el tablero a partir de
  // ESTA colocacion, y de ahi salen la rejilla de calibracion y el banco de
  // precision. Los dos sitios tienen que moverse juntos: que no coincidieran
  // fue la causa n.5 del 06/09 (sesgo vertical de 94 px, 9 de 12 fallos).
  const int win_w = 900, win_h = 640;
  RECT work_area;
  ::SystemParametersInfo(SPI_GETWORKAREA, 0, &work_area, 0);
  const int area_w = work_area.right - work_area.left;
  const int area_h = work_area.bottom - work_area.top;
  Win32Window::Point origin(
      work_area.left + (area_w - win_w) / 2,
      work_area.top + (area_h - win_h) / 2);
  Win32Window::Size size(win_w, win_h);
  if (!window.Create(L"interactor_gate", origin, size)) {
    return EXIT_FAILURE;
  }
  window.SetQuitOnClose(true);

  ::MSG msg;
  while (::GetMessage(&msg, nullptr, 0, 0)) {
    ::TranslateMessage(&msg);
    ::DispatchMessage(&msg);
  }

  ::CoUninitialize();
  return EXIT_SUCCESS;
}
