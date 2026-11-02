from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.views import generic
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.db import transaction
import logging

from .models import Course, Enrollment, Question, Choice, Submission

logger = logging.getLogger(__name__)


def registration_request(request):
    context = {}

    if request.method == 'GET':
        return render(
            request,
            'onlinecourse/user_registration_bootstrap.html',
            context
        )

    elif request.method == 'POST':
        username = request.POST['username']
        password = request.POST['psw']
        first_name = request.POST['firstname']
        last_name = request.POST['lastname']

        user_exist = User.objects.filter(username=username).exists()

        if not user_exist:
            user = User.objects.create_user(
                username=username,
                first_name=first_name,
                last_name=last_name,
                password=password
            )
            login(request, user)
            return redirect('onlinecourse:index')

        context['message'] = 'User already exists.'
        return render(
            request,
            'onlinecourse/user_registration_bootstrap.html',
            context
        )


def login_request(request):
    context = {}

    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['psw']

        user = authenticate(username=username, password=password)

        if user is not None:
            login(request, user)
            return redirect('onlinecourse:index')

        context['message'] = 'Invalid username or password.'
        return render(
            request,
            'onlinecourse/user_login_bootstrap.html',
            context
        )

    return render(
        request,
        'onlinecourse/user_login_bootstrap.html',
        context
    )


def logout_request(request):
    logout(request)
    return redirect('onlinecourse:index')


def check_if_enrolled(user, course):
    if user.is_authenticated:
        return Enrollment.objects.filter(
            user=user,
            course=course
        ).exists()

    return False


class CourseListView(generic.ListView):
    template_name = 'onlinecourse/course_list_bootstrap.html'
    context_object_name = 'course_list'

    def get_queryset(self):
        user = self.request.user
        courses = Course.objects.order_by('-total_enrollment')[:10]

        for course in courses:
            if user.is_authenticated:
                course.is_enrolled = check_if_enrolled(user, course)

        return courses


class CourseDetailView(generic.DetailView):
    model = Course
    template_name = 'onlinecourse/course_detail_bootstrap.html'


def enroll(request, course_id):
    course = get_object_or_404(Course, pk=course_id)
    user = request.user

    is_enrolled = check_if_enrolled(user, course)

    if not is_enrolled and user.is_authenticated:
        Enrollment.objects.create(
            user=user,
            course=course,
            mode='honor'
        )

        course.total_enrollment += 1
        course.save()

    return HttpResponseRedirect(
        reverse('onlinecourse:course_details', args=(course.id,))
    )


def extract_answers(request):
    submitted_answers = []

    for key in request.POST:
        if key.startswith('choice'):
            for value in request.POST.getlist(key):
                try:
                    submitted_answers.append(int(value))
                except (ValueError, TypeError):
                    continue

    return submitted_answers


@login_required
@transaction.atomic
def submit(request, course_id):
    if request.method != 'POST':
        return redirect('onlinecourse:course_details', pk=course_id)

    course = get_object_or_404(Course, pk=course_id)

    enrollment = get_object_or_404(
        Enrollment,
        user=request.user,
        course=course
    )

    submission = Submission.objects.create(
        enrollment=enrollment
    )

    answer_ids = extract_answers(request)

    selected_choices = Choice.objects.filter(
        id__in=answer_ids,
        question__course=course
    )

    submission.choices.add(*selected_choices)

    return redirect(
        'onlinecourse:show_exam_result',
        course_id=course.id,
        submission_id=submission.id
    )


@login_required
def show_exam_result(request, course_id, submission_id):
    course = get_object_or_404(Course, pk=course_id)

    submission = get_object_or_404(
        Submission,
        pk=submission_id,
        enrollment__user=request.user,
        enrollment__course=course
    )

    selected_choices = submission.choices.all()

    total_score = 0
    max_score = 0
    question_results = []

    for question in course.question_set.all():
        correct_choices = question.choice_set.filter(is_correct=True)

        selected_for_question = selected_choices.filter(
            question=question
        )

        correct_ids = set(
            correct_choices.values_list('id', flat=True)
        )

        selected_ids = set(
            selected_for_question.values_list('id', flat=True)
        )

        is_correct = (
            len(correct_ids) > 0
            and selected_ids == correct_ids
        )

        question_grade = question.grade
        max_score += question_grade

        grade_awarded = question_grade if is_correct else 0
        total_score += grade_awarded

        question_results.append({
            'question': question,
            'selected_choices': selected_for_question,
            'correct_choices': correct_choices,
            'is_correct': is_correct,
            'grade_awarded': grade_awarded,
            'grade': question_grade,
        })

    passed = total_score >= (max_score * 0.8) if max_score > 0 else False

    context = {
        'course': course,
        'submission': submission,
        'question_results': question_results,
        'total_score': total_score,
        'max_score': max_score,
        'passed': passed,
    }

    return render(
        request,
        'onlinecourse/exam_result_bootstrap.html',
        context
    )