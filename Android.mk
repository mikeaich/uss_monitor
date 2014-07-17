LOCAL_PATH:= $(call my-dir)

include $(CLEAR_VARS)
LOCAL_SRC_FILES:= procserver.c proc_report.c stack.c red_black_tree.c misc.c
LOCAL_MODULE := procserver
include $(BUILD_EXECUTABLE)
